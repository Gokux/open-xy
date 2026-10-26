// Private input check. Emits only into the maintainer's ignored output directory.
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {resolve} from 'node:path';
import assert from 'node:assert/strict';
import {openKit, linkKit, patchFirmware, recoverFirmware, readLdr, buildAssets, zipFiles} from '../builder/core.mjs';
const [directory, stockFile, content] = process.argv.slice(2);
const kit = await openKit(JSON.parse(readFileSync(resolve(directory, 'kit.json'))));
const stock = new Uint8Array(readFileSync(stockFile));
const catalog = new Uint8Array(readFileSync(resolve(content, 'op1_factory.json')));
assert.deepEqual(await recoverFirmware(kit, stock), {stock, selected:null});
for (let mask = 1; mask < 2 ** kit.machines.length; mask++) {
  const selected = kit.machines.filter((_, i) => mask & 2 ** i).map(m => m.id);
  const linked = linkKit(kit, selected), target = resolve(directory, 'reference', String(mask));
  const firmware = await patchFirmware(kit, linked, stock);
  const recovered = await recoverFirmware(kit, firmware);
  assert.deepEqual(recovered, {stock, selected});
  assert.deepEqual(await patchFirmware(kit, linkKit(kit, recovered.selected), recovered.stock), firmware);
  const profilingOff = await patchFirmware(kit, linked, stock, {profiling: false});
  assert.notDeepEqual(profilingOff, firmware);
  assert.deepEqual(await recoverFirmware(kit, profilingOff), {stock, selected});
  assert.deepEqual(await patchFirmware(kit, linkKit(kit, selected), stock, {profiling: false}), profilingOff);
  writeFileSync(target + '.profiling-off.ldr', profilingOff);
  const timingHooks = kit.profile.patches.filter(edit => edit.profiling === false);
  assert.ok(timingHooks.length > 1);
  const mixed = profilingOff.slice(), firstHook = timingHooks[0];
  const offset = Number(firstHook.file_offset);
  mixed.set(firmware.subarray(offset, offset + firstHook.length), offset);
  await assert.rejects(recoverFirmware(kit, mixed));
  const damagedLabel = firmware.slice();
  damagedLabel[Number(kit.profile.patches.at(-1).file_offset)] ^= 1;
  await assert.rejects(recoverFirmware(kit, damagedLabel));
  writeFileSync(target + '.ldr', firmware);
  const files = await buildAssets(kit, selected, catalog, linked.numbers);
  for (const [path, bytes] of Object.entries(files)) {
    const name = resolve(target, path); mkdirSync(resolve(name, '..'), {recursive: true}); writeFileSync(name, bytes);
  }
  writeFileSync(target + '.zip', zipFiles({'os.ldr': firmware, ...files}));
  const changed = stock.slice(); changed[50] ^= 1;
  await assert.rejects(patchFirmware(kit, linked, changed), /Only OP–XY OS 1.2.0 is supported/);
  await assert.rejects(patchFirmware(kit, linked, firmware), /Only OP–XY OS 1.2.0 is supported/);
  // Corruption outside allowed edits, inside a hook, and inside the module
  // must all reject, even when reversing the profile can recover stock bytes.
  for (const offset of [50, Number(kit.profile.patches[2].file_offset), readLdr(firmware).at(-2).offset + 16]) {
    const damaged = firmware.slice(); damaged[offset] ^= 1;
    await assert.rejects(recoverFirmware(kit, damaged));
  }
}
// Relinking does not depend on checkbox order or mutate the object capsules.
const all = kit.machines.map(m => m.id);
assert.deepEqual(linkKit(kit, all).module, linkKit(kit, [...all].reverse()).module);
console.log('Browser container/assets checks: all selections recovered in both profiling modes; corrupt/mixed inputs rejected.');
