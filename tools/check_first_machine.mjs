// Exercise the starter's documented audible edit using the real WASM modules.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PreviewEngine} from '../sdk/browser/engine.mjs';

function frequency(path) {
  const module = new WebAssembly.Module(readFileSync(path));
  // The starter's four controls; the module may expose further parameter words.
  const count = new WebAssembly.Instance(module, {}).exports.opxy_parameter_count();
  const controls = [0, 0x40000000, 0x53333333, 0x40000000];
  const engine = new PreviewEngine(module, 44100, Array.from({length: count}, (_, i) => controls[i] ?? 0));
  engine.noteOn(69);
  const samples = new Float32Array(44100);
  engine.render(samples);
  const crossings = [];
  for (let i = 2049; i < samples.length; i++) {
    if (samples[i - 1] <= 0 && samples[i] > 0) crossings.push(i);
  }
  assert.ok(crossings.length > 100, 'The starter must produce audible periodic output');
  const period = (crossings.at(-1) - crossings[0]) / (crossings.length - 1);
  return 44100 / period;
}
const original = frequency(process.argv[2]), changed = frequency(process.argv[3]);
assert.ok(Math.abs(original - 440) < 0.1, `Original pitch ${original}`);
assert.ok(Math.abs(changed - 220) < 0.1, `Changed pitch ${changed}`);
console.log(`PASS: tutorial edit changes A4 from ${original.toFixed(2)} Hz to ${changed.toFixed(2)} Hz.`);
