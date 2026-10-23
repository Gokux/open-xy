// SDK backend for a retained segment display with bounded inline text.
// Frame words: masks[characters], label[16 bytes], values[4][8 bytes], key,
// dials[4] as Q10 cos/sin pairs.
import { inputWords } from './controls.mjs';

// segments::Input: parameters[4], shown[4 bytes], slots[8].
const INPUT_BYTES = 52;
export class SegmentDisplay {
  constructor(module) {
    if (WebAssembly.Module.imports(module).length) throw new Error('Unexpected display imports');
    this.api = new WebAssembly.Instance(module).exports;
    const e = this.api;
    this.characters = e.opxy_segment_characters();
    const frameBytes = 4 * this.characters + 84;
    if (!Number.isInteger(this.characters) || this.characters < 1 || this.characters > 8 ||
        e.opxy_segment_input_bytes() !== INPUT_BYTES || e.opxy_segment_frame_bytes() !== frameBytes) {
      throw new Error('Unsupported segment frame');
    }
    const bytes = e.memory.buffer.byteLength, input = e.opxy_segment_input(), at = e.opxy_segment_frame();
    if (input % 4 || input <= 0 || input + INPUT_BYTES > bytes || at % 4 || at <= 0 || at + frameBytes > bytes ||
        (input < at + frameBytes && at < input + INPUT_BYTES)) throw new Error('Invalid segment storage');
    this.input = new Uint32Array(e.memory.buffer, input, INPUT_BYTES / 4);
    this.frame = new Uint32Array(e.memory.buffer, at, frameBytes / 4);
    this.stateBytes = 0; // Stateless author callback; the SDK owns the output frame/cache.
  }
  reset() {}
  // input: shownControls(words, shown) from controls.mjs.
  tick(input) {
    this.input.set(inputWords(input));
    if (this.api.opxy_segment_render() !== 1) throw new Error('Invalid segment output');
    return this.frame;
  }
}
const namespace = 'http://www.w3.org/2000/svg';
const decoder = new TextDecoder();
function text(frame, at, size) {
  const bytes = new Uint8Array(frame.buffer, frame.byteOffset + at, size);
  const end = bytes.indexOf(0);
  if (end < 0) throw new Error('Unbounded segment text');
  return decoder.decode(bytes.subarray(0, end));
}
// Elements and attributes of the authored subset the preview copies; never
// styles, links, event handlers or unknown XML.
const elements = new Set(['g', 'rect', 'circle', 'ellipse', 'line', 'polyline', 'polygon', 'path', 'text']);
const attributes = new Set(['id', 'd', 'x', 'y', 'width', 'height', 'cx', 'cy', 'r', 'rx', 'ry', 'x1', 'y1', 'x2', 'y2',
  'points', 'fill', 'stroke', 'stroke-width', 'stroke-linejoin', 'stroke-linecap', 'stroke-miterlimit', 'transform',
  'font-family', 'font-size', 'text-anchor']);
const dialPose = /^matrix\(1 0 0 1 ([-+]?(?:\d+(?:\.\d*)?|\.\d+)) ([-+]?(?:\d+(?:\.\d*)?|\.\d+))\)$/;
export class SegmentSvg {
  constructor(asset, bindings) {
    if (asset.length > 65536 || /<!DOCTYPE|<!ENTITY/i.test(asset)) throw new Error('Invalid segment asset');
    const parsed = new DOMParser().parseFromString(`<svg xmlns="${namespace}">${asset}</svg>`, 'image/svg+xml');
    if (parsed.querySelector('parsererror')) throw new Error('Malformed segment asset');
    const { nodes, glow, dials, palette, glowPalette, label } = bindings;
    const count = nodes.length;
    if (count < 14 || count > 112 || count % 14 || !Array.isArray(glow) || glow.length > 3 ||
        glow.some(layer => layer.length !== count) || glowPalette?.length !== glow.length ||
        !Array.isArray(dials) || dials.length > 4) throw new Error('Invalid segment bindings');
    const bound = [...nodes, ...glow.flat(), ...dials];
    if (new Set(bound).size !== bound.length) throw new Error('Invalid segment bindings');
    this.characters = count / 14;
    // The whole artwork, in authored order; bound leaves are found by ID.
    this.root = document.createElementNS(namespace, 'g');
    const copies = new Map();
    const copy = (source, parent) => {
      for (const child of source.children) {
        if (!elements.has(child.localName)) continue;
        const node = document.createElementNS(namespace, child.localName);
        for (const attr of child.attributes) if (attributes.has(attr.name)) node.setAttribute(attr.name, attr.value);
        if (child.localName === 'text') node.textContent = child.textContent;
        else copy(child, node);
        if (child.id) {
          if (copies.has(child.id)) throw new Error('Duplicate asset ID');
          copies.set(child.id, node);
        }
        parent.append(node);
      }
    };
    copy(parsed.documentElement, this.root);
    const leaf = (id, type) => {
      const node = copies.get(id);
      if (node?.localName !== type) throw new Error('Missing or foreign segment leaf');
      return node;
    };
    // A donor lends its fill, stroke and stroke width, as on the device.
    const paint = pair => {
      if (pair?.length !== 2) throw new Error('Expected lit/unlit palette');
      return pair.map(id => {
        const node = copies.get(id);
        const fill = node?.getAttribute('fill'), stroke = node?.getAttribute('stroke');
        if (![fill, stroke].every(value => /^#[0-9A-Fa-f]{6}$/.test(value))) throw new Error('Invalid segment palette');
        return { fill, stroke, width: node.getAttribute('stroke-width') };
      });
    };
    this.layers = [[nodes, palette], ...glow.map((layer, i) => [layer, glowPalette[i]])]
      .map(([ids, pair]) => ({ nodes: ids.map(id => leaf(id, 'path')), paint: paint(pair) }));
    this.dials = dials.map(id => {
      const node = leaf(id, 'path'), pose = dialPose.exec(node.getAttribute('transform') || '');
      if (!pose) throw new Error('Dial needs a translation-only pose');
      return { node, x: pose[1], y: pose[2], cos: 0, sin: 0 };
    });
    this.label = label && copies.has(label) ? leaf(label, 'text') : null;
    this.key = 0;
  }
  apply(frame) {
    if (!(frame instanceof Uint32Array) || frame.length !== this.characters + 21) throw new Error('Invalid segment frame');
    this.dials.forEach((dial, i) => {
      const cos = frame[this.characters + 13 + 2 * i] | 0, sin = frame[this.characters + 14 + 2 * i] | 0;
      if (dial.cos === cos && dial.sin === sin) return;
      const [a, b] = cos || sin ? [cos / 1024, sin / 1024] : [1, 0];
      dial.node.setAttribute('transform', `matrix(${a} ${b} ${-b} ${a} ${dial.x} ${dial.y})`);
      dial.cos = cos; dial.sin = sin;
    });
    const key = frame[this.characters + 12];
    if (this.key === key) return;
    for (const layer of this.layers) {
      for (let i = 0; i < layer.nodes.length; ++i) {
        const { fill, stroke, width } = layer.paint[frame[Math.floor(i / 14)] & (0x8000 >>> (i % 14)) ? 0 : 1];
        const node = layer.nodes[i];
        node.setAttribute('fill', fill); node.setAttribute('stroke', stroke); node.setAttribute('stroke-width', width);
      }
    }
    if (this.label) this.label.textContent = text(frame, 4 * this.characters, 16);
    this.key = key;
  }
  svg() { return new XMLSerializer().serializeToString(this.root); }
}
