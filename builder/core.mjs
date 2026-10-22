// Browser-only linker and container writer for a maintainer-curated kit.
// No compiler, device access, network requests, or arbitrary address input.
export function requireThat(ok, message) { if (!ok) throw new Error(message); }
const check = requireThat;
const utf8 = new TextEncoder();
const decoder = new TextDecoder('utf-8', {fatal: true});
const align = (n, a) => Math.ceil(n / a) * a;
const hex = bytes => Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
const unhex = s => {
  check(typeof s === 'string' && /^(?:[a-f0-9]{2})+$/.test(s), 'Invalid hex bytes');
  return Uint8Array.from(s.match(/../g), b => parseInt(b, 16));
};
export const decode64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
export const sha256 = async bytes => hex(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)));
export const equal = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
function view(bytes) { return new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength); }
function join(parts) {
  const output = new Uint8Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0; for (const p of parts) { output.set(p, at); at += p.length; } return output;
}

// Only ET_REL objects exported by the maintainer are accepted. SHF_MERGE and
// SHF_STRINGS are removed by the exporter, identically for GNU and this linker.
export function readObject(bytes) {
  check(bytes.length >= 52 && bytes.length <= 2 ** 20, 'Object size outside bounds');
  const d = view(bytes), u16 = at => d.getUint16(at, true), u32 = at => d.getUint32(at, true);
  check(hex(bytes.subarray(0, 6)) === '7f454c460101' && u16(16) === 1 && u16(18) === 106,
    'Expected a Blackfin relocatable object');
  const start = u32(32), count = u16(48), namesIndex = u16(50);
  check(u16(46) === 40 && count > 0 && count < 4096 && namesIndex < count && start + count * 40 <= bytes.length,
    'Invalid object section table');
  const sections = Array.from({length: count}, (_, index) => {
    const at = start + index * 40;
    const s = {index, nameOffset: u32(at), type: u32(at + 4), flags: u32(at + 8),
      offset: u32(at + 16), size: u32(at + 20), link: u32(at + 24), info: u32(at + 28),
      alignment: u32(at + 32) || 1, stride: u32(at + 36)};
    check(s.size <= 2 ** 20 && s.alignment <= 4096 && (s.alignment & (s.alignment - 1)) === 0,
      'Invalid object section size/alignment');
    check(s.type === 8 || s.offset + s.size <= bytes.length, 'Object section exceeds file');
    s.data = s.type === 8 ? new Uint8Array() : bytes.subarray(s.offset, s.offset + s.size);
    return s;
  });
  const string = (table, at) => {
    check(at < table.length, 'Invalid object string offset');
    const end = table.indexOf(0, at); check(end >= at, 'Unterminated object string');
    return decoder.decode(table.subarray(at, end));
  };
  const groups = ['text', 'rodata', 'data', 'bss'];
  for (const s of sections) {
    s.name = string(sections[namesIndex].data, s.nameOffset);
    if (!(s.flags & 2)) continue;
    check(!(s.flags & ~7), 'Unsupported allocated section flags');
    const n = s.name;
    s.group = /^(\.rodata(?:\.|$)|\.data\.rel\.ro(?:\.|$))/.test(n) ? 'rodata'
      : /^(\.data(?:\.|$)|\.sdata(?:\.|$))/.test(n) ? 'data'
      : /^(\.bss(?:\.|$)|\.sbss(?:\.|$))/.test(n) ? 'bss'
      : /^\.text(?:\.|$)/.test(n) ? 'text' : null;
    check(groups.includes(s.group) && s.type === (s.group === 'bss' ? 8 : 1),
      'Unsupported allocated section: ' + n);
  }
  const tables = sections.filter(s => s.type === 2);
  check(tables.length === 1, 'Expected one symbol table');
  const table = tables[0];
  check(table.stride === 16 && table.size % 16 === 0 && table.link < count, 'Invalid symbol table');
  const symbols = Array.from({length: table.size / 16}, (_, i) => {
    const at = table.offset + i * 16, info = bytes[at + 12], section = u16(at + 14);
    check(section < count || section === 0xfff1, 'COMMON and extended symbol sections are unsupported');
    return {name: string(sections[table.link].data, u32(at)), value: u32(at + 4), size: u32(at + 8),
      binding: info >> 4, type: info & 15, section};
  });
  const relocations = [], touched = new Set();
  for (const s of sections) {
    check(s.type !== 9, 'REL without explicit addends is unsupported');
    if (s.type !== 4) continue;
    check(s.link === table.index && s.info < count && s.stride === 12 && s.size % 12 === 0,
      'Invalid relocation table');
    check(sections[s.info].group && sections[s.info].type !== 8, 'Relocation target is not initialized memory');
    for (let at = s.offset; at < s.offset + s.size; at += 12) {
      const info = u32(at + 4), type = info & 255, symbol = info >>> 8;
      check([6, 7, 10, 13, 18].includes(type) && symbol < symbols.length, 'Unsupported relocation');
      const offset = u32(at), size = type === 18 ? 4 : 2;
      check(offset % 2 === 0 && offset + size <= sections[s.info].size &&
        (![10, 13].includes(type) || offset >= 2), 'Relocation exceeds section');
      for (let i = [10, 13].includes(type) ? offset - 2 : offset; i < offset + size; i++) {
        const key = s.info + ':' + i;
        check(!touched.has(key), 'Overlapping relocations'); touched.add(key);
      }
      relocations.push({section: s.info, offset, type, symbol, addend: d.getInt32(at + 8, true)});
    }
  }
  return {sections, symbols, relocations};
}

// Assignments are catalog-wide, independent of selection order. New IDs are
// curated once, then remain reserved even when their machine is deselected.
export function identities(kit, saved = null) {
  const seen = {engine: new Set(), effect: new Set(), page: new Set()}, result = {};
  for (const m of kit.machines) {
    check(!Object.hasOwn(result, m.id), 'Duplicate machine identity');
    const id = m.identity;
    for (const kind of ['engine', 'effect', 'page']) {
      if (id[kind] === undefined) continue;
      const n = id[kind];
      const valid = kind === 'engine' ? n === 26 || n >= 34 && n < 63
        : kind === 'effect' ? [1, 2, 3, 4, 6, 7, 8, 11].includes(n)
        : m.kind === 'effect' ? n === 21 : m.stockPage ? n === 2 || n === 7 : n === 50 || n >= 82 && n < 128;
      check(Number.isInteger(n) && valid, 'Identity overlaps a stock slot or exceeds capacity');
      if (kind !== 'page' || !m.stockPage && m.kind !== 'effect') {
        check(!seen[kind].has(n), 'Conflicting ' + kind + ' assignment'); seen[kind].add(n);
      }
    }
    check(Number.isInteger(id.page) && Number.isInteger(id[m.kind === 'effect' ? 'effect' : 'engine']),
      'Incomplete machine identity');
    result[m.id] = {...id};
  }
  if (saved) {
    check(saved.format === 'opxy-kit/1' && saved.profile === kit.profile.id && Array.isArray(saved.selected),
      'Layout belongs to a different firmware profile');
    for (const [id, assigned] of Object.entries(saved.identities ?? {})) {
      check(result[id] && assigned && Object.keys(assigned).length === Object.keys(result[id]).length &&
        Object.entries(result[id]).every(([key, value]) => assigned[key] === value),
        'Saved identity has changed: ' + id);
    }
    check(saved.selected.every(id => result[id] && Object.hasOwn(saved.identities, id)),
      'Layout contains an unknown machine or missing identity');
  }
  return result;
}

// Relocated stock engine records and screen slots at the end of the reservation.
export const TABLE_BYTES = 4096;
export async function openKit(kit) {
  check(kit.format === 'opxy-browser-kit/1' && kit.machines.length > 0 && kit.machines.length <= 32,
    'Unsupported curated kit');
  identities(kit);
  const profileBytes = decode64(kit.profileSource);
  check(await sha256(profileBytes) === '4c5f3727c8560612bc48b8358d1a6d34626be98dfb3272a3ecc7264adf3d4dbe' &&
    JSON.stringify(JSON.parse(decoder.decode(profileBytes))) === JSON.stringify(kit.profile),
    'Firmware edit profile is not the reviewed profile');
  check(kit.profile.module_base === 0x8d450d60 && kit.profile.reserved_bytes === 0x80000 &&
    kit.limits?.module === kit.profile.reserved_bytes - TABLE_BYTES &&
    kit.profile.stock_sha256 === 'e9dbdaa16e39446b267bee4c9e7256c491d167a1594a3a97343af35d74bc98f2',
    'Unsupported firmware profile');
  // The bundled stock menu is authenticated where it is used (buildAssets).
  check(typeof kit.stockCatalog === 'string' && kit.stockCatalog.length <= 2 * 1024 ** 2, 'Missing bundled stock menu');
  check(typeof kit.screenTemplate === 'string' &&
    await sha256(utf8.encode(kit.screenTemplate)) === '88ed06af444dd76773dd905204577f0f1eeca548a8cdd92dc760e6ae67147e4e',
    'Platform screen template differs from the supported ABI');
  const ids = new Set(kit.machines.map(m => m.id)), names = new Set();
  const objects = [];
  for (const o of kit.objects) {
    check(!names.has(o.name) && (o.owner === null || ids.has(o.owner)), 'Duplicate or unowned object');
    names.add(o.name);
    const bytes = decode64(o.bytes);
    check(await sha256(bytes) === o.sha256, 'Curated object hash mismatch: ' + o.name);
    objects.push({...o, ...readObject(bytes)});
  }
  return {...kit, objects};
}

export function linkKit(kit, selection) {
  identities(kit);
  check(Array.isArray(selection) && selection.length > 0 && new Set(selection).size === selection.length &&
    selection.every(id => kit.machines.some(m => m.id === id)), 'Choose distinct curated machines');
  const selected = new Set(selection);
  const objects = kit.objects.filter(o => o.owner === null || selected.has(o.owner));
  const globals = new Map(Object.entries(kit.definitions)), placements = new Map(), segments = [];
  let cursor = kit.profile.module_base, initializedEnd;
  for (const group of ['text', 'rodata', 'data', 'bss']) {
    const all = objects.flatMap(o => o.sections.filter(s => s.group === group).map(s => ({o, s})));
    cursor = align(cursor, Math.max(group === 'text' ? 1 : 4, ...all.map(({s}) => s.alignment)));
    for (const {o, s} of all) {
      cursor = align(cursor, s.alignment);
      placements.set(o.name + ':' + s.index, cursor);
      if (s.size) segments.push({owner: o.owner, name: s.name, group, address: cursor, size: s.size});
      cursor += s.size;
      if (cursor > kit.profile.module_base + kit.limits.module) {
        // One pool for every machine's code, data and state: say who uses it.
        const used = new Map();
        for (const x of objects) for (const y of x.sections) if (y.group) used.set(x.owner ?? 'sdk', (used.get(x.owner ?? 'sdk') || 0) + y.size);
        const shares = [...used].sort((a, b) => b[1] - a[1]).map(([owner, size]) => `${owner} ${(size / 1024).toFixed(1)} KiB`);
        check(false, `Selection exceeds the ${kit.limits.module / 1024} KiB module memory: ${shares.join(', ')}`);
      }
    }
    if (group === 'data') initializedEnd = cursor;
  }
  const allocated = cursor - kit.profile.module_base, initialized = initializedEnd - kit.profile.module_base;
  const bssStart = Math.min(cursor, ...segments.filter(s => s.group === 'bss').map(s => s.address));
  check(initialized > 0, 'Empty module');
  const definedValue = (o, s) => {
    if (s.section === 0xfff1) return s.value;
    const base = placements.get(o.name + ':' + s.section);
    check(base !== undefined && s.value + s.size <= o.sections[s.section].size, 'Symbol outside allocated section: ' + s.name);
    return base + s.value;
  };
  for (const o of objects) for (const s of o.symbols) {
    if (!s.section || !s.binding || !s.name || s.type === 4) continue;
    check(s.binding === 1, 'Weak/global binding is unsupported');
    check(!globals.has(s.name), 'Duplicate global symbol: ' + s.name);
    globals.set(s.name, definedValue(o, s));
  }
  // Only SDK startup and sample dispatch can use absent-machine callbacks.
  const aliases = new Map();
  for (const m of kit.machines) if (!selected.has(m.id)) {
    for (const [symbol, fallback] of Object.entries(m.absent)) {
      check(!globals.has(symbol) && globals.has(fallback), 'Invalid absent-machine callback');
      aliases.set(symbol, globals.get(fallback));
    }
  }
  const module = new Uint8Array(initialized), out = view(module);
  for (const o of objects) {
    for (const s of o.sections) if (s.group && s.type !== 8 && s.size) {
      module.set(s.data, placements.get(o.name + ':' + s.index) - kit.profile.module_base);
    }
    for (const r of o.relocations) {
      const sym = o.symbols[r.symbol], address = placements.get(o.name + ':' + r.section) + r.offset;
      const S = sym.section ? definedValue(o, sym) : globals.get(sym.name) ??
        (o.name === kit.startup || (o.owner === null && ['sdk/sample_routes.o', 'sdk/sample_callbacks.o'].includes(o.name) &&
          kit.machines.some(m => m.kind === 'sample' && (sym.name === m.prefix + '_ready' ||
            (o.name === 'sdk/sample_callbacks.o' && ['assign', 'migrate', 'control', 'panel', 'prepare_begin', 'prepare_step', 'prepare_words', 'prepare_result']
              .some(c => sym.name === m.prefix + '_sample_' + c)))))
          ? aliases.get(sym.name) : undefined);
      check(S !== undefined, 'Unresolved import: ' + sym.name);
      const value = S + r.addend, offset = address - kit.profile.module_base;
      check(Number.isSafeInteger(value) && value >= 0 && value <= 0xffffffff, 'Symbol arithmetic overflow');
      if (r.type === 18) out.setUint32(offset, value, true);
      else if (r.type === 6) out.setUint16(offset, value & 0xffff, true);
      else if (r.type === 7) out.setUint16(offset, Math.floor(value / 65536), true);
      else {
        const opcode = out.getUint16(offset - 2, true), delta = value - (address - 2);
        check((opcode & 0xff00) === (r.type === 10 ? 0xe300 : 0xe200) &&
          delta % 2 === 0 && delta >= -(2 ** 24) && delta < 2 ** 24, 'Invalid or out-of-range relative branch');
        const encoded = delta / 2 & 0xffffff;
        out.setUint16(offset - 2, (opcode & 0xff00) | encoded >>> 16, true);
        out.setUint16(offset, encoded & 0xffff, true);
      }
    }
  }
  return {module, globals, aliases, objects, segments,
    sizes: {initialized, bss: cursor - bssStart, allocated, available: kit.limits.module - allocated}};
}

export function readLdr(bytes) {
  check(bytes.length > 0 && bytes.length <= 16 * 1024 ** 2, 'LDR size outside bounds');
  const d = view(bytes), blocks = []; let at = 0;
  while (at < bytes.length) {
    check(blocks.length < 10000 && at + 16 <= bytes.length, 'Invalid loader record');
    const code = d.getUint32(at, true), target = d.getUint32(at + 4, true), count = d.getUint32(at + 8, true);
    check(code >>> 24 === 0xad && bytes.subarray(at, at + 16).reduce((a, b) => a ^ b, 0) === 0,
      'Invalid loader signature/checksum');
    const fill = Boolean(code & 256), stored = fill ? 0 : count;
    check(target + count <= 2 ** 32 && at + 16 + stored <= bytes.length, 'Loader range overflow');
    blocks.push({offset: at, code, target, count, fill, argument: d.getUint32(at + 12, true)});
    at += 16 + stored;
    if (code & 0x8000) { check(at === bytes.length, 'Trailing bytes after FINAL'); return blocks; }
  }
  throw new Error('Missing FINAL record');
}
function header(flags, target, count, argument) {
  const bytes = new Uint8Array(16), d = view(bytes);
  [0xad000000 | flags, target, count, argument].forEach((v, i) => d.setUint32(i * 4, v, true));
  bytes[2] = bytes.reduce((a, b) => a ^ b, 0); return bytes;
}
const hooks = new Map([
  [0x8d5063b2, ['extensions_synth_exit', false]],
  [0x8d5231e4, ['extensions_screen_exit', false]], [0x8d523240, ['extensions_screen_exit', false]],
  [0x8d4e09d6, ['extensions_catalog_checked', true]], [0x8d4e0b78, ['extensions_catalog_checked', true]],
  [0x8d5b5b38, ['extensions_sample_classify', false]], [0x8d5ab9a0, ['extensions_sample_note_region', true]],
  [0x8d50b5d8, ['sdk_sample_cache_destroy', true]],
  [0x8d51de40, ['sdk_sample_progress_frame', true]],
  [0x8d4dad2e, ['sdk_sample_cache_snapshot', true]],
  [0x8d4d957e, ['sdk_sample_cache_ipc_priority', true]],
  [0x8d4d9e26, ['sdk_sample_cache_gui_add', true]],
  [0x8d4d8ede, ['sdk_sample_cache_audio_add', true]],
  [0x8d4d9dde, ['sdk_sample_cache_reset', true]],
  [0x8d4d8e88, ['sdk_sample_cache_reset', true]],
  [0x8d50bf1c, ['sdk_sample_cache_worker', true]],
  [0x8d4d9dd2, ['sdk_sample_cache_send', true]],
  [0x8c0b1e76, ['sdk_sample_ui_engine', true]],
  [0x8c0b21c6, ['sdk_sample_region_control', true]],
  [0x8c0b3290, ['sdk_sample_press_engine', true]],
  [0x8d5ab6da, ['sdk_sample_live_pitch_kind', true]],
  [0x8d58d9ca, ['sdk_sample_octave_store', true]],
  [0x8c0a2cee, ['sdk_sample_assignment_frames', true]],
  [0x8c0a2de4, ['sdk_sample_assign_region', true]],
  [0x8d5882d8, ['sdk_sample_assign_fade', true]],
  [0x8d5878a8, ['extensions_sample_key', false]],
  [0x8d5347de, ['sdk_sample_drum_display', true]],
  [0x8d53465a, ['sdk_sample_drum_range', true]],
  [0x8d5349e4, ['sdk_sample_drum_fade', true]],
  [0x8c0a21c0, ['sdk_sample_pending_retry', true]],
  [0x8c0a219c, ['sdk_sample_active_retry', true]],
]);
export async function patchFirmware(kit, linked, stock) {
  const p = kit.profile;
  check(stock.length === p.stock_bytes && await sha256(stock) === p.stock_sha256,
    'Choose the original, decrypted OP–XY 1.2.0 os.ldr. Encrypted .tfw and previously patched files are unsupported.');
  const blocks = readLdr(stock), first = blocks[0], final = blocks.at(-1);
  check(blocks.length === 999 && first.count === 0 && (first.code & 0xffff) === 0x5004 &&
    final.count === 0 && (final.code & 0xffff) === 0x8004, 'Unexpected stock loader layout');
  const low = p.module_base, high = low + p.reserved_bytes;
  const overlaps = blocks.filter(b => b.target < high && low < b.target + b.count);
  check(overlaps.length === 1 && overlaps[0].fill && overlaps[0].argument === 0 &&
    overlaps[0].target === p.heap_fill_base && overlaps[0].count === p.heap_fill_bytes &&
    overlaps[0].target <= low && overlaps[0].target + overlaps[0].count >= high,
    'Reservation is not covered by the unchanged stock zero-fill');
  check(linked.module.length > 0 && linked.sizes.allocated <= kit.limits.module &&
    p.patches.length === 48,
    'Module or patch set exceeds its profile');
  const patched = stock.slice(), touched = new Set();
  for (const edit of p.patches) {
    const site = Number(edit.address), offset = Number(edit.file_offset), before = unhex(edit.before);
    let after = unhex(edit.after);
    const covering = blocks.filter(b => b.target < site + before.length && site < b.target + b.count);
    check(covering.length === 1 && !covering[0].fill && covering[0].target <= site &&
      site + before.length <= covering[0].target + covering[0].count &&
      covering[0].offset + 16 + site - covering[0].target === offset &&
      equal(stock.subarray(offset, offset + before.length), before), 'Patch preimage/mapping mismatch');
    if (site === 0x8c0b9114) {
      const destination = linked.globals.get('kit_startup_label');
      check(destination >= low && destination < low + linked.module.length && destination % 2 === 0,
        'Startup label destination outside module');
      after = new Uint8Array(10);
      [0xdc00, destination >>> 16, destination & 0xffff, 0, 0].forEach((word, i) => view(after).setUint16(i * 2, word, true));
    } else if (hooks.has(site)) {
      const [symbol, call] = hooks.get(site), destination = linked.globals.get(symbol), delta = destination - site;
      check(Number.isInteger(destination) && destination >= low && destination < low + linked.module.length && destination % 2 === 0,
        'Hook destination outside module');
      if (edit.length === 8) {
        check(call, 'Eight-byte hook must be a call');
        after = new Uint8Array(8);
        [0xde00, destination >>> 16, destination & 0xffff, 0].forEach((word, i) => view(after).setUint16(i * 2, word, true));
      } else {
        check(delta % 2 === 0 && delta >= -(2 ** 24) && delta < 2 ** 24, 'Hook branch out of range');
        const value = delta / 2 & 0xffffff; after = new Uint8Array(edit.length);
        view(after).setUint16(0, (call ? 0xe300 : 0xe200) | value >>> 16, true);
        view(after).setUint16(2, value & 0xffff, true);
      }
    }
    check(before.length === edit.length && after.length === edit.length, 'Patch length mismatch');
    for (let i = 0; i < edit.length; i++) {
      check(!touched.has(offset + i), 'Overlapping patch intervals'); touched.add(offset + i);
    }
    patched.set(after, offset);
  }
  const at = final.offset;
  const candidate = join([patched.subarray(0, at), header(4, low, linked.module.length, 0), linked.module, patched.subarray(at)]);
  candidate.set(header(0x5004, first.target, 0, candidate.length - 16));
  const result = readLdr(candidate);
  check(result.length === blocks.length + 1 && equal(candidate.subarray(-16), stock.subarray(-16)), 'Loader entry changed');
  const restored = join([candidate.subarray(0, at), candidate.subarray(at + 16 + linked.module.length)]);
  restored.set(stock.subarray(0, 16));
  for (const edit of p.patches) restored.set(unhex(edit.before), Number(edit.file_offset));
  check(equal(restored, stock), 'Unauthorized change outside reviewed OS edits');
  return candidate;
}

// Recover only an exact output of this curated collection. The uploaded module
// is compared with freshly linked code, never executed or reused for a build.
export async function recoverFirmware(kit, input) {
  const p = kit.profile;
  if (input.length === p.stock_bytes && await sha256(input) === p.stock_sha256) {
    readLdr(input);
    return {stock: input.slice(), selected: null};
  }
  check(kit.machines.length <= 4, 'Recovery supports the reviewed four-machine collection only');
  const blocks = readLdr(input), first = blocks[0], module = blocks.at(-2), final = blocks.at(-1);
  check(blocks.length === p.stock_records + 1 && first.count === 0 &&
    (first.code & 0xffff) === 0x5004 && first.argument === input.length - 16 &&
    final.count === 0 && (final.code & 0xffff) === 0x8004 &&
    module.offset === p.stock_bytes - 16 && (module.code & 0xffff) === 4 &&
    module.target === p.module_base && module.argument === 0 &&
    module.count > 0 && module.count <= kit.limits.module &&
    input.length === p.stock_bytes + 16 + module.count,
    'This is not a recognized Open-XY firmware layout');
  const stock = join([input.subarray(0, module.offset), input.subarray(final.offset)]);
  stock.set(header(0x5004, first.target, 0, stock.length - 16));
  for (const edit of p.patches) stock.set(unhex(edit.before), Number(edit.file_offset));
  check(await sha256(stock) === p.stock_sha256,
    'Cannot recover the exact stock 1.2.0 firmware from this file');
  const payload = input.subarray(module.offset + 16, final.offset);
  // Reconstruct every selection's entire image; never trust the uploaded
  // module or infer ownership from its label. At most 15 deterministic links.
  // Yield between candidates so file changes and navigation remain responsive;
  // the caller discards stale results.
  for (let mask = 1; mask < 2 ** kit.machines.length; mask++) {
    const selected = kit.machines.filter((_, i) => mask & 2 ** i).map(m => m.id);
    const linked = linkKit(kit, selected);
    if (equal(linked.module, payload) && equal(await patchFirmware(kit, linked, stock), input))
      return {stock, selected};
    await new Promise(resolve => setTimeout(resolve, 0));
  }
  throw new Error('This patched firmware does not match this collection. Choose a supported Open-XY build or original stock 1.2.0 os.ldr.');
}

export function presetPath(machine) {
  if (machine.kind === 'effect') return null;
  check(['synth', 'sample'].includes(machine.kind) && /^[a-z][a-z0-9_]{0,14}$/.test(machine.id),
    'Invalid preset instrument');
  return `content/presets/${machine.id}/default.json`;
}

function defaultPreset(machine) {
  const entry = JSON.parse(machine.catalog.trim().replace(/^,/, ''));
  check(/^[a-z][a-z0-9_]{0,14}$/.test(entry.type) && Array.isArray(entry.default_params) &&
    entry.default_params.length === 8 && entry.default_params.every(n => Number.isInteger(n) && n >= 0 && n <= 32767),
    'Invalid preset engine or defaults');
  const defaults = machine.presetDefaults ?? {};
  check(defaults && typeof defaults === 'object' && !Array.isArray(defaults) &&
    Object.keys(defaults).every(key => key === 'amp'), 'Invalid preset defaults');
  const amp = defaults.amp ?? {};
  check(amp && typeof amp === 'object' && !Array.isArray(amp) &&
    Object.entries(amp).every(([key, value]) => ['attack', 'decay', 'release', 'sustain'].includes(key) &&
      Number.isInteger(value) && value >= 0 && value <= 32767), 'Invalid preset amp defaults');
  // Authored init settings in the device's version-4 preset structure. Engine
  // controls come from its catalog, never from a copied factory sound.
  return {
    engine: {
      bendrange: 8191, highpass: 0,
      modulation: Object.fromEntries(['aftertouch', 'modwheel', 'pitchbend', 'velocity']
        .map(source => [source, {amount: 16384, target: 0}])),
      params: [...entry.default_params], playmode: 'poly',
      'portamento.amount': 0, 'portamento.type': 0, transpose: 0,
      'tuning.root': 0, 'tuning.scale': 0, 'velocity.sensitivity': 0, volume: 8192, width: 0,
    },
    envelope: {
      // Match a device-saved minimum amp release: the stored endpoint is 32767.
      amp: {attack: 128, decay: 8192, release: 32767, sustain: 32767, ...amp},
      filter: {attack: 0, decay: 0, release: 0, sustain: 32767},
    },
    fx: {active: false, params: [0, 0, 0, 0, 0, 32767, 0, 0], type: 'svf'},
    lfo: {active: false, params: [0, 0, 0, 0, 0, 0, 0, 0], type: 'value'},
    octave: 0, platform: 'OP-XY', regions: [], type: entry.type, version: 4,
  };
}

export async function buildAssets(kit, selection, catalog) {
  check(await sha256(catalog) === kit.profile.stock_catalog_sha256, 'Choose the original stock content/op1_factory.json');
  const machines = kit.machines.filter(m => selection.includes(m.id));
  const entries = machines.filter(m => m.kind !== 'effect').map(m => m.catalog);
  let text = decoder.decode(catalog);
  const boundary = 4435;
  text = decoder.decode(catalog.subarray(0, boundary)) + entries.join('') + decoder.decode(catalog.subarray(boundary));
  const effects = machines.filter(m => m.kind === 'effect');
  if (effects.length) {
    const start = text.indexOf('"fx_types"'), end = text.indexOf('\n    ]', start);
    check(start >= 0 && end > start, 'Missing FX catalog boundary');
    text = text.slice(0, end) + effects.map(m => m.catalog).join('') + text.slice(end);
  }
  const base = JSON.parse(decoder.decode(catalog)), expected = {...base,
    engine_types: [...base.engine_types, ...entries.map(s => JSON.parse(s.trim().replace(/^,/, '')))],
    fx_types: [...base.fx_types, ...effects.map(m => JSON.parse(m.catalog.trim().replace(/^,/, '')))]};
  check(JSON.stringify(JSON.parse(text)) === JSON.stringify(expected), 'Unexpected catalog modification');
  const files = {'content/op1_factory.json': utf8.encode(text)};
  for (const machine of machines) {
    const path = presetPath(machine);
    if (path) files[path] = utf8.encode(JSON.stringify(defaultPreset(machine), null, 2) + '\n');
  }
  if (machines.some(m => m.artwork)) {
    check(await sha256(utf8.encode(kit.screenTemplate)) ===
      '88ed06af444dd76773dd905204577f0f1eeca548a8cdd92dc760e6ae67147e4e', 'Platform screen template differs from the supported ABI');
    const baseSvg = kit.screenTemplate;
    check(baseSvg.split('</svg>').length === 2, 'Unexpected stock artwork boundary');
    for (const m of machines.filter(m => m.artwork)) {
      check(/^[a-z][a-z0-9_]*\.svg$/.test(m.asset), 'Invalid artwork filename');
      files['content/display/' + m.asset] = utf8.encode(baseSvg.replace('</svg>', m.artwork + '</svg>'));
    }
  }
  return files;
}

// Stored ZIP: no dependencies or compression worker, deterministic metadata.
export function zipFiles(files) {
  const locals = [], central = []; let offset = 0;
  const crc32 = bytes => {
    let c = 0xffffffff;
    for (const b of bytes) { c ^= b; for (let i = 0; i < 8; i++) c = c >>> 1 ^ (c & 1 ? 0xedb88320 : 0); }
    return (c ^ 0xffffffff) >>> 0;
  };
  for (const [name, bytes] of Object.entries(files)) {
    check(/^[a-zA-Z0-9_./-]+$/.test(name) && !name.includes('..') && !name.startsWith('/'), 'Invalid bundle path');
    const path = utf8.encode(name), crc = crc32(bytes), local = new Uint8Array(30 + path.length), d = view(local);
    d.setUint32(0, 0x04034b50, true); d.setUint16(4, 20, true); d.setUint16(12, 33, true);
    d.setUint32(14, crc, true); d.setUint32(18, bytes.length, true); d.setUint32(22, bytes.length, true);
    d.setUint16(26, path.length, true); local.set(path, 30);
    const entry = new Uint8Array(46 + path.length), e = view(entry);
    e.setUint32(0, 0x02014b50, true); e.setUint16(4, 20, true); e.setUint16(6, 20, true); e.setUint16(14, 33, true);
    e.setUint32(16, crc, true); e.setUint32(20, bytes.length, true); e.setUint32(24, bytes.length, true);
    e.setUint16(28, path.length, true); e.setUint32(42, offset, true); entry.set(path, 46);
    locals.push(local, bytes); central.push(entry); offset += local.length + bytes.length;
  }
  const directory = join(central), end = new Uint8Array(22), e = view(end);
  e.setUint32(0, 0x06054b50, true); e.setUint16(8, central.length, true); e.setUint16(10, central.length, true);
  e.setUint32(12, directory.length, true); e.setUint32(16, offset, true);
  return join([...locals, directory, end]);
}
