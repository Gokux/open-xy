// MTP over WebUSB for an OP–XY in "mtp file transfer (mac)" mode. Sends files
// to paths below the device's top level, creating missing folders. The only
// deletion is a same-named file the caller agreed to replace; folders are never
// replaced or deleted. Windows binds its own MTP driver, so WebUSB cannot open
// the device there; Windows keeps the File Explorer steps.

const VENDOR = 0x2367, VENDOR_CLASS = 0xff, ROOT = 0xffffffff;
const COMMAND = 1, DATA = 2, RESPONSE = 3;
const OK = 0x2001, SESSION_ALREADY_OPEN = 0x201e;
const OPEN_SESSION = 0x1002, CLOSE_SESSION = 0x1003, STORAGE_IDS = 0x1004, OBJECT_HANDLES = 0x1007,
  OBJECT_INFO = 0x1008, DELETE_OBJECT = 0x100b, SEND_OBJECT_INFO = 0x100c, SEND_OBJECT = 0x100d;
const UNDEFINED_FORMAT = 0x3000, FOLDER_FORMAT = 0x3001;
// A multiple of every bulk packet size, so only the final transfer can be short.
const CHUNK = 1 << 20;
const refusals = {
  0x200c: 'Your OP–XY is full. Free some space, then try again.',
  0x200d: 'Your OP–XY’s storage is read-only.',
  0x200f: 'Your OP–XY refused access to that file.',
};

// The browser can't name the app holding the device; these are the ones that do.
export const BUSY = 'Another app is using your OP–XY. Quit Field Kit, OpenMTP or Android File Transfer, then try again.';
export const supported = () => globalThis.isSecureContext && !!globalThis.navigator?.usb;

function concat(...parts) {
  const out = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0; for (const p of parts) { out.set(p, at); at += p.length; }
  return out;
}
const words = values => {
  const out = new Uint8Array(values.length * 4), view = new DataView(out.buffer);
  values.forEach((value, i) => view.setUint32(i * 4, value, true)); return out;
};
const view = bytes => new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
export function container(type, code, transaction, payload = new Uint8Array(0)) {
  const header = new Uint8Array(12), v = view(header);
  v.setUint32(0, 12 + payload.length, true); v.setUint16(4, type, true);
  v.setUint16(6, code, true); v.setUint32(8, transaction, true);
  return concat(header, payload);
}
// PTP strings: a UTF-16 code-unit count including the terminator, then UTF-16LE.
export function ptpString(value) {
  const units = value ? value + '\0' : '';
  if (units.length > 255) throw new Error('That file name is too long for your OP–XY.');
  const out = new Uint8Array(1 + units.length * 2), v = view(out);
  out[0] = units.length;
  for (let i = 0; i < units.length; i++) v.setUint16(1 + i * 2, units.charCodeAt(i), true);
  return out;
}
export function readString(bytes, at) {
  const v = view(bytes); let text = '';
  for (let i = 0; i < bytes[at]; i++) text += String.fromCharCode(v.getUint16(at + 1 + i * 2, true));
  return text.replace(/\0$/, '');
}
// ObjectInfo dataset; the filename follows the fixed fields. A folder is a
// generic association (type 1) with no data.
export function objectInfo(storage, name, size, parent = ROOT, folder = false) {
  const fixed = new Uint8Array(52), v = view(fixed);
  v.setUint32(0, storage, true); v.setUint16(4, folder ? FOLDER_FORMAT : UNDEFINED_FORMAT, true);
  v.setUint32(8, size, true); v.setUint32(38, parent, true);
  if (folder) v.setUint16(42, 1, true);
  return concat(fixed, ptpString(name), ptpString(''), ptpString(''), ptpString(''));
}
const readParams = bytes => Array.from({length: Math.floor(bytes.length / 4)}, (_, i) => view(bytes).getUint32(i * 4, true));
function readWords(bytes) {
  const v = view(bytes), count = v.getUint32(0, true);
  if (bytes.length < 4 + count * 4) throw new Error('Unexpected reply from your OP–XY.');
  return Array.from({length: count}, (_, i) => v.getUint32(4 + i * 4, true));
}
// A relative path of plain names, such as content/display/macroosc.svg.
function segments(path) {
  const names = String(path).split('/');
  for (const name of names) {
    if (!name || name === '.' || name === '..' || /[\\\0]/.test(name)) throw new Error(`${path} isn’t a file path your OP–XY accepts.`);
    ptpString(name);
  }
  return names;
}

export class Device {
  #device; #number; #in; #out; #packet; #transaction = 0; #current; #storage; #running = false; #folders; #listings;
  static async request(usb = navigator.usb) {
    return new Device(await usb.requestDevice({filters: [{vendorId: VENDOR, classCode: VENDOR_CLASS}]}));
  }
  constructor(device) { this.#device = device; }
  async open() {
    const device = this.#device;
    await device.open();
    if (!device.configuration) await device.selectConfiguration(1);
    const found = device.configuration.interfaces.find(i => {
      const a = i.alternate;
      return a.interfaceClass === VENDOR_CLASS && ['in', 'out'].every(d => a.endpoints.some(e => e.type === 'bulk' && e.direction === d));
    });
    if (!found) {
      await device.close().catch(() => {});
      throw new Error('Your OP–XY isn’t in Mac file transfer mode. On the factory menu, press track 2.');
    }
    try { await device.claimInterface(found.interfaceNumber); }
    catch { await device.close().catch(() => {}); throw new Error(BUSY); }
    this.#number = found.interfaceNumber;
    const endpoint = d => found.alternate.endpoints.find(e => e.type === 'bulk' && e.direction === d);
    this.#in = endpoint('in').endpointNumber; this.#out = endpoint('out').endpointNumber;
    this.#packet = endpoint('out').packetSize;
    this.#transaction = 0;
    const opened = await this.#run(OPEN_SESSION, [1]);
    if (opened.code !== SESSION_ALREADY_OPEN) this.#expect(opened, 'open file transfer');
    const [storage] = readWords(this.#expect(await this.#run(STORAGE_IDS), 'find its storage').payload);
    if (storage === undefined) throw new Error('Your OP–XY has no storage available.');
    this.#storage = storage;
    this.#folders = new Map([['', ROOT]]);
    this.#listings = new Map();
  }
  // Names in one folder, mapped to their object handles. Listed once per
  // session and kept current as this client adds and deletes objects.
  async #children(parent) {
    if (this.#listings.has(parent)) return this.#listings.get(parent);
    const {payload} = this.#expect(await this.#run(OBJECT_HANDLES, [this.#storage, 0, parent]), 'list its files');
    const files = new Map();
    for (const handle of readWords(payload)) {
      const info = this.#expect(await this.#run(OBJECT_INFO, [handle]), 'list its files').payload;
      files.set(readString(info, 52), {handle, folder: view(info).getUint16(4, true) === FOLDER_FORMAT});
    }
    this.#listings.set(parent, files);
    return files;
  }
  // The handle of a folder path, creating missing folders on the way.
  async #folder(names, onStep) {
    let parent = ROOT, path = '';
    for (const name of names) {
      path = path ? path + '/' + name : name;
      if (this.#folders.has(path)) { parent = this.#folders.get(path); continue; }
      const siblings = await this.#children(parent), existing = siblings.get(name);
      if (existing && !existing.folder) throw new Error(`Your OP–XY has a file named ${path} where a folder is needed.`);
      const handle = existing?.handle ?? this.#expect(await this.#run(SEND_OBJECT_INFO, [this.#storage, parent],
        objectInfo(this.#storage, name, 0, parent, true)), 'create the folder ' + path).params[2];
      if (!existing) {
        siblings.set(name, {handle, folder: true}); this.#listings.set(handle, new Map());
        onStep('folder', path);
      }
      parent = handle;
      this.#folders.set(path, parent);
    }
    return parent;
  }
  // Sends one file, such as os.ldr or content/op1_factory.json. Returns false
  // when a same-named file exists and replace() declines. onStep reports
  // ('folder', path) for each folder created and ('replace', path) before a
  // replacement.
  async send(path, bytes, {replace = async () => false, onProgress = () => {}, onStep = () => {}} = {}) {
    const names = segments(path), name = names.pop();
    if (bytes.length > 0xffffffff - 12) throw new Error('That file is too large for your OP–XY.');
    const parent = await this.#folder(names, onStep);
    const siblings = await this.#children(parent), existing = siblings.get(name);
    if (existing?.folder) throw new Error(`Your OP–XY already has a folder named ${path}.`);
    if (existing) {
      if (!await replace(path)) return false;
      onStep('replace', path);
      this.#expect(await this.#run(DELETE_OBJECT, [existing.handle, 0]), 'replace ' + path);
      siblings.delete(name);
    }
    const {params} = this.#expect(await this.#run(SEND_OBJECT_INFO, [this.#storage, parent],
      objectInfo(this.#storage, name, bytes.length, parent)), 'accept ' + path);
    this.#expect(await this.#run(SEND_OBJECT, [], bytes, onProgress), 'save ' + path);
    siblings.set(name, {handle: params[2], folder: false});
    return true;
  }
  // Safe to call at any time. A pending transfer is cancelled with the MTP class
  // Cancel Request so the device isn't left waiting for the rest of a file.
  async close() {
    const device = this.#device;
    if (!device.opened) return;
    if (this.#running) await this.#cancel();
    else if (this.#storage !== undefined) await this.#run(CLOSE_SESSION).catch(() => {});
    this.#storage = undefined;
    if (this.#number !== undefined) await device.releaseInterface(this.#number).catch(() => {});
    await device.close().catch(() => {});
  }
  async #cancel() {
    const request = new Uint8Array(6);
    view(request).setUint16(0, 0x4001, true); view(request).setUint32(2, this.#current, true);
    await this.#device.controlTransferOut({requestType: 'class', recipient: 'interface', request: 0x64, value: 0,
      index: this.#number}, request).catch(() => {});
    for (const [direction, endpoint] of [['out', this.#out], ['in', this.#in]]) {
      await this.#device.clearHalt(direction, endpoint).catch(() => {});
    }
  }
  #expect(result, action) {
    if (result.code !== OK) {
      throw new Error(refusals[result.code] ?? `Your OP–XY couldn’t ${action} (MTP error 0x${result.code.toString(16)}).`);
    }
    return result;
  }
  async #run(code, params = [], data = null, onProgress = () => {}) {
    const id = this.#current = this.#transaction++;
    this.#running = true;
    try {
      await this.#send(container(COMMAND, code, id, words(params)));
      if (data) await this.#send(container(DATA, code, id, data), onProgress);
      let reply = await this.#receive(), payload = null;
      if (reply.type === DATA) { payload = reply.payload; reply = await this.#receive(); }
      if (reply.type !== RESPONSE || reply.id !== id) throw new Error('Unexpected reply from your OP–XY.');
      return {code: reply.code, payload, params: readParams(reply.payload)};
    } finally { this.#running = false; }
  }
  async #send(bytes, onProgress = () => {}) {
    for (let at = 0; at < bytes.length; at += CHUNK) {
      const result = await this.#device.transferOut(this.#out, bytes.subarray(at, at + CHUNK));
      if (result.status !== 'ok') throw new Error('Your OP–XY stopped responding. Reconnect it, then try again.');
      onProgress(Math.min(1, (at + CHUNK) / bytes.length));
    }
    // A transfer ending exactly on a packet boundary needs a zero-length packet.
    if (bytes.length % this.#packet === 0) await this.#device.transferOut(this.#out, new Uint8Array(0));
  }
  async #read() {
    const result = await this.#device.transferIn(this.#in, CHUNK);
    if (result.status !== 'ok') throw new Error('Your OP–XY stopped responding. Reconnect it, then try again.');
    return new Uint8Array(result.data.buffer, result.data.byteOffset, result.data.byteLength);
  }
  async #receive() {
    let first;
    do first = await this.#read(); while (!first.length);  // skip a trailing zero-length packet
    if (first.length < 12) throw new Error('Unexpected reply from your OP–XY.');
    const v = view(first), length = v.getUint32(0, true), parts = [first];
    for (let have = first.length; have < length;) {
      const more = await this.#read();
      if (!more.length) throw new Error('Unexpected reply from your OP–XY.');
      parts.push(more); have += more.length;
    }
    const whole = concat(...parts).subarray(0, length);
    return {type: v.getUint16(4, true), code: v.getUint16(6, true), id: v.getUint32(8, true), payload: whole.subarray(12)};
  }
}
