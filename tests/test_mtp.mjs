import test from 'node:test';
import assert from 'node:assert/strict';
import {BUSY, Device, container, objectInfo, ptpString, readString} from '../builder/mtp.mjs';

// A WebUSB stand-in answering as an OP–XY in "mtp file transfer (mac)" mode:
// one storage, top-level parent 0xffffffff, and Invalid Parent Object for 0.
// No device, permission or hardware is used here.
const STORAGE = 0x10001, ROOT = 0xffffffff, PACKET = 512;
const le = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
function fakeDevice({files = {}, busy = false, refuse = null, split = false} = {}) {
  const state = {opened: false, claimed: null, ops: [], zeroLength: 0, sent: new Map(Object.entries(files)), deleted: []};
  const handles = new Map([...state.sent.keys()].map((name, i) => [i + 1, name]));
  let next = handles.size + 1, pending = null, incoming = [], expected = 0, outgoing = [];
  const reply = (type, code, id, payload = new Uint8Array(0)) => {
    const whole = container(type, code, id, payload);
    if (!split) { outgoing.push(whole); return; }
    // Packet-sized pieces with a trailing zero-length packet, as on the wire.
    for (let at = 0; at < whole.length; at += PACKET) outgoing.push(whole.subarray(at, at + PACKET));
    if (whole.length % PACKET === 0) outgoing.push(new Uint8Array(0));
  };
  const words = values => { const out = new Uint8Array(4 + values.length * 4); le(out).setUint32(0, values.length, true); values.forEach((v, i) => le(out).setUint32(4 + i * 4, v, true)); return out; };
  function command(code, id, params, data) {
    state.ops.push(code.toString(16));
    if (refuse && code === refuse.code) return reply(3, refuse.response, id);
    if (code === 0x1002 || code === 0x1003) return reply(3, 0x2001, id);
    if (code === 0x1004) { reply(2, code, id, words([STORAGE])); return reply(3, 0x2001, id); }
    if (code === 0x1007) {
      assert.deepEqual(params, [STORAGE, 0, ROOT]);
      reply(2, code, id, words([...handles.keys()])); return reply(3, 0x2001, id);
    }
    if (code === 0x1008) {
      // A null entry stands for a folder.
      const name = handles.get(params[0]), entry = state.sent.get(name), info = objectInfo(STORAGE, name, entry?.length ?? 0);
      if (entry === null) le(info).setUint16(4, 0x3001, true);
      reply(2, code, id, info); return reply(3, 0x2001, id);
    }
    if (code === 0x100b) {
      const name = handles.get(params[0]); handles.delete(params[0]); state.sent.delete(name); state.deleted.push(name);
      return reply(3, 0x2001, id);
    }
    if (code === 0x100c) {
      if (params[0] !== STORAGE || params[1] !== ROOT || le(data).getUint32(38, true) !== ROOT) return reply(3, 0x201a, id);
      pending = {name: readString(data, 52), size: le(data).getUint32(8, true)};
      return reply(3, 0x2001, id, Uint8Array.from([...new Uint8Array(new Uint32Array([STORAGE, ROOT, next]).buffer)]));
    }
    if (code === 0x100d) {
      assert.ok(pending, 'SendObject without SendObjectInfo');
      assert.equal(data.length, pending.size);
      state.sent.set(pending.name, data); handles.set(next++, pending.name); pending = null;
      return reply(3, 0x2001, id);
    }
    return reply(3, 0x2005, id);
  }
  let open = null;
  const device = {
    get opened() { return state.opened; },
    configuration: null,
    async open() { state.opened = true; },
    async close() { state.opened = false; state.claimed = null; },
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
      if (!chunk.length) { state.zeroLength++; return {status: 'ok', bytesWritten: 0}; }
      incoming.push(chunk); expected ||= le(chunk).getUint32(0, true);
      const have = incoming.reduce((n, c) => n + c.length, 0);
      if (have < expected) return {status: 'ok', bytesWritten: chunk.length};
      const whole = new Uint8Array(have); let at = 0; for (const c of incoming) { whole.set(c, at); at += c.length; }
      incoming = []; expected = 0;
      const v = le(whole), type = v.getUint16(4, true), code = v.getUint16(6, true), id = v.getUint32(8, true);
      const body = whole.subarray(12);
      if (type === 1) {
        const params = Array.from({length: body.length / 4}, (_, i) => le(body).getUint32(i * 4, true));
        if ([0x100c, 0x100d].includes(code)) open = {code, id, params};
        else command(code, id, params);
      } else {
        assert.equal(type, 2); assert.deepEqual([code, id], [open.code, open.id]);
        command(code, id, open.params, body.slice()); open = null;
      }
      return {status: 'ok', bytesWritten: chunk.length};
    },
    async transferIn(endpoint) {
      assert.equal(endpoint, 9);
      const next = outgoing.shift(); assert.ok(next, 'read with nothing to answer');
      return {status: 'ok', data: new DataView(next.buffer, next.byteOffset, next.byteLength)};
    },
  };
  return {device, state};
}

test('PTP strings round trip and match the wire layout', () => {
  assert.deepEqual([...ptpString('')], [0]);
  assert.deepEqual([...ptpString('os.ldr')], [7, 111,0,115,0,46,0,108,0,100,0,114,0,0,0]);
  assert.equal(readString(ptpString('Ünïcode name.json'), 0), 'Ünïcode name.json');
  assert.throws(() => ptpString('x'.repeat(255)), /too long/);
});

test('sends a file to the top level with the parent the OP–XY accepts', async () => {
  const {device, state} = fakeDevice({split: true}), mtp = new Device(device);
  const bytes = Uint8Array.from({length: 3 * 1024 * 1024 + 5}, (_, i) => i * 7);
  const progress = [];
  await mtp.open();
  assert.equal(await mtp.sendToRoot('os.ldr', bytes, {onProgress: p => progress.push(p)}), true);
  await mtp.close();
  assert.deepEqual(state.sent.get('os.ldr'), bytes);
  assert.deepEqual(state.ops, ['1002', '1004', '1007', '100c', '100d', '1003']);
  assert.equal(progress.at(-1), 1);
  assert.equal(state.opened, false); assert.equal(state.claimed, null);
});

test('ends a packet-aligned transfer with a zero-length packet', async () => {
  // 12-byte data header + 500 bytes = exactly one 512-byte packet.
  const {device, state} = fakeDevice(), mtp = new Device(device);
  await mtp.open(); await mtp.sendToRoot('aligned.bin', new Uint8Array(500)); await mtp.close();
  assert.equal(state.zeroLength, 1);
  assert.equal(state.sent.get('aligned.bin').length, 500);
});

test('asks before replacing a top-level file and never replaces a folder', async () => {
  const {device, state} = fakeDevice({files: {'os.ldr': Uint8Array.of(1), content: null}}), mtp = new Device(device);
  await mtp.open();
  const asked = [];
  assert.equal(await mtp.sendToRoot('os.ldr', Uint8Array.of(2), {replace: async name => { asked.push(name); return false; }}), false);
  assert.deepEqual([state.deleted, [...state.sent.get('os.ldr')]], [[], [1]]);
  assert.equal(await mtp.sendToRoot('os.ldr', Uint8Array.of(2), {replace: async () => true}), true);
  assert.deepEqual([state.deleted, [...state.sent.get('os.ldr')], asked], [['os.ldr'], [2], ['os.ldr']]);
  await assert.rejects(mtp.sendToRoot('content', Uint8Array.of(3)), /already has a folder named content/);
  assert.equal(state.sent.get('content'), null);
  await mtp.close();
});

test('explains a device held by another app and releases it', async () => {
  const {device, state} = fakeDevice({busy: true});
  await assert.rejects(new Device(device).open(), error => error.message === BUSY);
  assert.equal(state.opened, false);
});

test('reports device refusals in plain language', async () => {
  const {device} = fakeDevice({refuse: {code: 0x100c, response: 0x200c}}), mtp = new Device(device);
  await mtp.open();
  await assert.rejects(mtp.sendToRoot('big.bin', Uint8Array.of(1)), /full/);
  await mtp.close();
  const other = fakeDevice({refuse: {code: 0x100d, response: 0x2002}}), second = new Device(other.device);
  await second.open();
  await assert.rejects(second.sendToRoot('x.bin', Uint8Array.of(1)), /couldn’t save x\.bin \(MTP error 0x2002\)/);
  await second.close();
});

test('rejects names that would leave the top level', async () => {
  const {device} = fakeDevice(), mtp = new Device(device);
  await mtp.open();
  for (const name of ['', '.', '..', 'content/os.ldr', '..\\os.ldr', 'a\0b']) {
    await assert.rejects(mtp.sendToRoot(name, Uint8Array.of(1)), /plain file name/, JSON.stringify(name));
  }
  await mtp.close();
});
