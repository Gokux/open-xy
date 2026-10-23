import test from 'node:test';
import assert from 'node:assert/strict';
import {BUSY, Device, container, objectInfo, ptpString, readString} from '../builder/mtp.mjs';

// A WebUSB stand-in answering as an OP–XY in "mtp file transfer (mac)" mode:
// one storage, top-level parent 0xffffffff, and Invalid Parent Object for 0 or
// any handle that isn't a folder. No device, permission or hardware is used.
const STORAGE = 0x10001, ROOT = 0xffffffff, PACKET = 512;
const le = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
// `files` maps paths to bytes, or to null for a folder.
function fakeDevice({files = {}, busy = false, refuse = null, split = false} = {}) {
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
      const reply = outgoing.shift(); assert.ok(reply, 'read with nothing to answer');
      return {status: 'ok', data: new DataView(reply.buffer, reply.byteOffset, reply.byteLength)};
    },
  };
  return {device, state};
}
const stock = {'os.ldr': Uint8Array.of(1), 'content/op1_factory.json': Uint8Array.of(1), 'content/display/stock.svg': Uint8Array.of(7),
  'content/presets/stock/default.json': Uint8Array.of(7), 'content/samples': null, 'user': null};

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
  assert.equal(await mtp.send('os.ldr', bytes, {onProgress: p => progress.push(p)}), true);
  await mtp.close();
  assert.deepEqual(state.read('os.ldr'), bytes);
  assert.deepEqual(state.ops, ['1002', '1004', '1007', '100c', '100d', '1003']);
  assert.equal(progress.at(-1), 1);
  assert.equal(state.opened, false); assert.equal(state.claimed, null);
});

test('sends a whole build into existing folders, replacing files and keeping other content', async () => {
  const {device, state} = fakeDevice({files: stock}), mtp = new Device(device);
  const build = {'os.ldr': Uint8Array.of(2), 'layout.json': Uint8Array.of(2), 'content/op1_factory.json': Uint8Array.of(2),
    'content/display/macroosc.svg': Uint8Array.of(2), 'content/presets/macroosc/default.json': Uint8Array.of(2),
    'content/presets/fm2op/default.json': Uint8Array.of(2)};
  const asked = [], steps = [];
  await mtp.open();
  for (const [path, bytes] of Object.entries(build)) {
    assert.equal(await mtp.send(path, bytes, {replace: async p => { asked.push(p); return true; }, onStep: (...step) => steps.push(step.join(' '))}), true);
  }
  await mtp.close();
  assert.deepEqual(steps, ['replace os.ldr', 'replace content/op1_factory.json', 'folder content/presets/macroosc', 'folder content/presets/fm2op']);
  for (const [path, bytes] of Object.entries(build)) assert.deepEqual(state.read(path), bytes, path);
  assert.deepEqual(asked, ['os.ldr', 'content/op1_factory.json']);
  assert.deepEqual(state.paths(), ['content/', 'content/display/', 'content/display/macroosc.svg', 'content/display/stock.svg',
    'content/op1_factory.json', 'content/presets/', 'content/presets/fm2op/', 'content/presets/fm2op/default.json',
    'content/presets/macroosc/', 'content/presets/macroosc/default.json', 'content/presets/stock/',
    'content/presets/stock/default.json', 'content/samples/', 'layout.json', 'os.ldr', 'user/']);
  assert.deepEqual(state.read('content/display/stock.svg'), Uint8Array.of(7));
});

test('ends a packet-aligned transfer with a zero-length packet', async () => {
  // 12-byte data header + 500 bytes = exactly one 512-byte packet.
  const {device, state} = fakeDevice(), mtp = new Device(device);
  await mtp.open(); await mtp.send('aligned.bin', new Uint8Array(500)); await mtp.close();
  assert.equal(state.zeroLength, 1);
  assert.equal(state.read('aligned.bin').length, 500);
});

test('asks before replacing a file and never replaces a folder', async () => {
  const {device, state} = fakeDevice({files: stock}), mtp = new Device(device);
  await mtp.open();
  assert.equal(await mtp.send('content/op1_factory.json', Uint8Array.of(2)), false);
  assert.deepEqual([state.deleted, state.read('content/op1_factory.json')], [[], Uint8Array.of(1)]);
  await assert.rejects(mtp.send('content/samples', Uint8Array.of(3), {replace: async () => true}), /already has a folder named content\/samples/);
  await assert.rejects(mtp.send('os.ldr/inner.txt', Uint8Array.of(3)), /file named os\.ldr where a folder is needed/);
  assert.equal(state.read('content/samples'), null);
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
  await assert.rejects(mtp.send('big.bin', Uint8Array.of(1)), /full/);
  await mtp.close();
  const other = fakeDevice({refuse: {code: 0x100d, response: 0x2002}}), second = new Device(other.device);
  await second.open();
  await assert.rejects(second.send('content/x.bin', Uint8Array.of(1)), /couldn’t save content\/x\.bin \(MTP error 0x2002\)/);
  await second.close();
});

test('rejects paths that would leave the device or name nothing', async () => {
  const {device} = fakeDevice(), mtp = new Device(device);
  await mtp.open();
  for (const path of ['', '/os.ldr', 'content//x', '../os.ldr', 'content/../os.ldr', 'content/./x', 'a\\b', 'a\0b', 'content/']) {
    await assert.rejects(mtp.send(path, Uint8Array.of(1)), /isn’t a file path/, JSON.stringify(path));
  }
  await mtp.close();
});
