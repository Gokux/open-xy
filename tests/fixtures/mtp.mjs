import assert from 'node:assert/strict';
import {container, objectInfo, readString} from '../../builder/mtp.mjs';

// A WebUSB stand-in answering as an OP–XY in "mtp file transfer (mac)" mode:
// one storage, top-level parent 0xffffffff, and Invalid Parent Object for 0 or
// any handle that isn't a folder. No device, permission or hardware is used.
const STORAGE = 0x10001, ROOT = 0xffffffff, PACKET = 512;
const le = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
// `files` maps paths to bytes, or to null for a folder.
// `strictToggle`: like some embedded stacks, clearing a halt that wasn't set desyncs the
// endpoint's data toggle, so the device drops the next packet. `stallOnce` stalls one
// transfer in that direction until it's cleared.
export function fakeDevice({files = {}, busy = false, refuse = null, split = false, hang = null, corrupt = null, strictToggle = false, stallOnce = null} = {}) {
  const objects = new Map(), state = {opened: false, claimed: null, ops: [], zeroLength: 0, deleted: []};
  let next = 1;
  const find = (parent, name) => [...objects].find(([, o]) => o.parent === parent && o.name === name)?.[0];
  const add = (parent, name, data) => { const handle = next++; objects.set(handle, {parent, name, data}); return handle; };
  for (const [path, data] of Object.entries(files)) {
    let parent = ROOT; const names = path.split('/'), name = names.pop();
    for (const folder of names) parent = find(parent, folder) ?? add(parent, folder, null);
    add(parent, name, data);
  }
  state.read = path => {
    let handle = ROOT;
    for (const name of path.split('/')) { handle = find(handle, name); if (!handle) return undefined; }
    return objects.get(handle).data;
  };
  state.paths = () => [...objects.keys()].map(handle => {
    const parts = []; for (let h = handle; h !== ROOT; h = objects.get(h).parent) parts.unshift(objects.get(h).name);
    return parts.join('/') + (objects.get(handle).data === null ? '/' : '');
  }).sort();
  let pending = null, incoming = [], expected = 0, outgoing = [], open = null;
  const reply = (type, code, id, payload = new Uint8Array(0)) => {
    const whole = container(type, code, id, payload);
    if (corrupt && type === 2 && code === 0x1009) corrupt(whole);
    if (!split) { outgoing.push(whole); return; }
    // Packet-sized pieces with a trailing zero-length packet, as on the wire.
    for (let at = 0; at < whole.length; at += PACKET) outgoing.push(whole.subarray(at, at + PACKET));
    if (whole.length % PACKET === 0) outgoing.push(new Uint8Array(0));
  };
  const words = values => { const out = new Uint8Array(4 + values.length * 4); le(out).setUint32(0, values.length, true); values.forEach((v, i) => le(out).setUint32(4 + i * 4, v, true)); return out; };
  const params = values => new Uint8Array(new Uint32Array(values).buffer);
  const isFolder = handle => handle === ROOT || objects.get(handle)?.data === null;
  function command(code, id, args, data) {
    state.ops.push(code.toString(16));
    if (refuse && code === refuse.code) return reply(3, refuse.response, id);
    if (code === hang) return;  // Never answers; only cancelling ends the wait.
    if (code === 0x1002 || code === 0x1003) return reply(3, 0x2001, id);
    if (code === 0x1004) { reply(2, code, id, words([STORAGE])); return reply(3, 0x2001, id); }
    if (code === 0x1007) {
      assert.deepEqual(args.slice(0, 2), [STORAGE, 0]);
      if (!isFolder(args[2])) return reply(3, 0x201a, id);
      reply(2, code, id, words([...objects].filter(([, o]) => o.parent === args[2]).map(([h]) => h))); return reply(3, 0x2001, id);
    }
    if (code === 0x1008) {
      const {name, data: bytes} = objects.get(args[0]);
      reply(2, code, id, objectInfo(STORAGE, name, bytes?.length ?? 0, ROOT, bytes === null)); return reply(3, 0x2001, id);
    }
    if (code === 0x1009) {
      const bytes = objects.get(args[0])?.data;
      if (!bytes) return reply(3, 0x2009, id);
      reply(2, code, id, bytes); return reply(3, 0x2001, id);
    }
    if (code === 0x100b) {
      const object = objects.get(args[0]);
      assert.notEqual(object.data, null, 'a folder was deleted');
      objects.delete(args[0]); state.deleted.push(object.name); return reply(3, 0x2001, id);
    }
    if (code === 0x100c) {
      const [storage, parent] = args;
      if (storage !== STORAGE || !isFolder(parent) || le(data).getUint32(38, true) !== parent) return reply(3, 0x201a, id);
      const name = readString(data, 52);
      if (find(parent, name)) return reply(3, 0x2019, id);
      if (le(data).getUint16(4, true) === 0x3001) {
        assert.equal(le(data).getUint16(42, true), 1, 'folders are generic associations');
        return reply(3, 0x2001, id, params([STORAGE, parent, add(parent, name, null)]));
      }
      pending = {parent, name, size: le(data).getUint32(8, true)};
      return reply(3, 0x2001, id, params([STORAGE, parent, next]));
    }
    if (code === 0x100d) {
      assert.ok(pending, 'SendObject without SendObjectInfo');
      assert.equal(data.length, pending.size);
      add(pending.parent, pending.name, data); pending = null;
      return reply(3, 0x2001, id);
    }
    return reply(3, 0x2005, id);
  }
  const device = {
    get opened() { return state.opened; },
    configuration: null,
    async open() { state.opened = true; },
    async close() { state.opened = false; state.claimed = null; state.abort?.(new DOMException('The transfer was cancelled.', 'AbortError')); },
    async controlTransferOut(setup, data) { state.control = {...setup, data: [...new Uint8Array(data)]}; return {status: 'ok'}; },
    // Get Device Status: busy once after a cancel, then OK.
    async controlTransferIn(setup) {
      assert.equal(setup.request, 0x67); state.statusPolls = (state.statusPolls ?? 0) + 1;
      return {status: 'ok', data: new DataView(Uint8Array.of(4, 0, ...(state.statusPolls === 1 ? [0x19, 0x20] : [0x01, 0x20])).buffer)};
    },
    async clearHalt(direction, endpoint) {
      (state.halts ??= []).push(direction + ' ' + endpoint);
      if (state.stalled === direction) state.stalled = null;
      else if (strictToggle && direction === 'out') state.desync = true;
    },
    async selectConfiguration() {
      device.configuration = {interfaces: [{interfaceNumber: 0, alternate: {interfaceClass: 255, endpoints: [
        {direction: 'out', type: 'bulk', endpointNumber: 10, packetSize: PACKET},
        {direction: 'in', type: 'bulk', endpointNumber: 9, packetSize: PACKET},
        {direction: 'in', type: 'interrupt', endpointNumber: 11, packetSize: 64}]}}]};
    },
    async claimInterface(n) { if (busy) throw new DOMException('Unable to claim interface.', 'NetworkError'); state.claimed = n; },
    async releaseInterface() { state.claimed = null; },
    async transferOut(endpoint, bytes) {
      assert.equal(endpoint, 10); assert.ok(state.claimed === 0);
      const chunk = Uint8Array.from(bytes);
      if (stallOnce === 'out' && !state.stallUsed) { state.stallUsed = true; state.stalled = 'out'; }
      if (state.stalled === 'out') return {status: 'stall', bytesWritten: 0};
      if (state.desync) { state.desync = false; state.dropped = (state.dropped ?? 0) + 1; return {status: 'ok', bytesWritten: chunk.length}; }
      if (!chunk.length) { state.zeroLength++; return {status: 'ok', bytesWritten: 0}; }
      incoming.push(chunk); expected ||= le(chunk).getUint32(0, true);
      const have = incoming.reduce((n, c) => n + c.length, 0);
      if (have < expected) return {status: 'ok', bytesWritten: chunk.length};
      const whole = new Uint8Array(have); let at = 0; for (const c of incoming) { whole.set(c, at); at += c.length; }
      incoming = []; expected = 0;
      const v = le(whole), type = v.getUint16(4, true), code = v.getUint16(6, true), id = v.getUint32(8, true);
      const body = whole.subarray(12);
      if (type === 1) {
        const args = Array.from({length: body.length / 4}, (_, i) => le(body).getUint32(i * 4, true));
        if ([0x100c, 0x100d].includes(code)) open = {code, id, args};
        else command(code, id, args);
      } else {
        assert.equal(type, 2); assert.deepEqual([code, id], [open.code, open.id]);
        command(code, id, open.args, body.slice()); open = null;
      }
      return {status: 'ok', bytesWritten: chunk.length};
    },
    async transferIn(endpoint) {
      assert.equal(endpoint, 9);
      const reply = outgoing.shift();
      if (!reply && hang) return new Promise((_, reject) => { state.abort = reject; });
      assert.ok(reply, 'read with nothing to answer');
      return {status: 'ok', data: new DataView(reply.buffer, reply.byteOffset, reply.byteLength)};
    },
  };
  return {device, state};
}
