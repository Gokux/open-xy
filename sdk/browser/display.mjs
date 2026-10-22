// Generic main-thread host for the bounded retained-asset drawing contract.
// Animation/state math lives entirely in the compiled contributor callback.
const integer = (value, low, high, name) => {
  if (!Number.isInteger(value) || value < low || value > high) throw new Error(`Invalid ${name}`);
  return value;
};

export class PreviewDisplay {
  constructor(module) {
    if (!(module instanceof WebAssembly.Module) || WebAssembly.Module.imports(module).length) {
      throw new Error('Display requires a self-contained compiled module');
    }
    this.api = new WebAssembly.Instance(module).exports;
    const e = this.api;
    if (e.opxy_display_abi() !== 1 || e.opxy_display_input_bytes() !== 32) throw new Error('Unsupported drawing ABI');
    this.stateBytes = integer(e.opxy_display_state_bytes(), 4, e.memory.buffer.byteLength, 'display state size');
    // Largest declared frame: 4 paths of 64 points and 64 nodes.
    const frameBytes = integer(e.opxy_display_frame_bytes(), 4, 4 * 516 + 64 * 20, 'drawing frame size');
    this.memory = e.memory.buffer;
    const ranges = [
      [e.opxy_display_state(), this.stateBytes], [e.opxy_display_input(), 32], [e.opxy_display_frame(), frameBytes],
    ];
    for (let i = 0; i < ranges.length; i++) {
      const [at, size] = ranges[i];
      integer(at, 4, this.memory.byteLength - size, 'display storage');
      if (at % 4 || size % 4) throw new Error('Misaligned drawing storage');
      for (let j = 0; j < i; j++) {
        if (at < ranges[j][0] + ranges[j][1] && ranges[j][0] < at + size) throw new Error('Overlapping drawing storage');
      }
    }
    this.input = new Uint32Array(this.memory, ranges[1][0], 8);
    this.frame = new Int32Array(this.memory, ranges[2][0], frameBytes / 4);
    this.reset();
  }
  reset() { this.api.opxy_display_reset(); }
  tick(parameters, elapsed, serial, track = 0, reducedMotion = false) {
    if (!Array.isArray(parameters) || parameters.length !== 4 || typeof reducedMotion !== 'boolean') {
      throw new Error('Invalid display input');
    }
    // Validate the complete snapshot before mutating input/state.
    for (const parameter of parameters) integer(parameter, 0, 0x7fffffff, 'display parameter');
    integer(elapsed, -0x80000000, 0x7fffffff, 'elapsed Q10 seconds');
    integer(serial, 0, 0xffffffff, 'note serial');
    integer(track, 0, 0xffffffff, 'track identity');
    if (this.api.memory.buffer !== this.memory) throw new Error('Display memory changed');
    this.input.set([...parameters, elapsed >>> 0, track, serial, Number(reducedMotion)]);
    this.api.opxy_display_render();
    if (this.api.opxy_display_valid() !== 1) throw new Error('Display emitted an invalid drawing frame');
    return this.frame;
  }
}

const SVG = 'http://www.w3.org/2000/svg';
const decimal = word => String(Math.round(word / 1024 * 1000) / 1000);
const attributeNames = new Set(['id', 'd', 'cx', 'cy', 'r', 'transform', 'fill', 'stroke', 'stroke-width', 'stroke-linejoin']);

export class SvgDisplay {
  constructor(asset, bindings) {
    if (typeof asset !== 'string' || asset.length > 65536 || /<!DOCTYPE|<!ENTITY/i.test(asset)) {
      throw new Error('Invalid drawing asset');
    }
    const { nodes, palette, paths, points } = bindings;
    if (!Array.isArray(paths) || paths.length < 1 || paths.length > 4 || paths.some((p, i) => p !== i) ||
        !Number.isInteger(points) || points < 2 || points > 64 ||
        nodes.length < paths.length || nodes.length > 64 || palette.length < 1 || palette.length > 16) {
      throw new Error('Unsupported retained asset bindings');
    }
    this.points = points;
    this.frameWords = paths.length * (1 + 2 * points) + 5 * nodes.length;
    const ids = [...bindings.nodes, ...bindings.palette];
    if (new Set(ids).size !== ids.length || ids.some(id => !/^[a-zA-Z_][a-zA-Z0-9_]*$/.test(id))) {
      throw new Error('Invalid retained asset identities');
    }
    const parsed = new DOMParser().parseFromString(`<svg xmlns="${SVG}">${asset}</svg>`, 'image/svg+xml');
    if (parsed.querySelector('parsererror')) throw new Error('Malformed drawing asset');
    const originals = new Map();
    for (const element of parsed.querySelectorAll('[id]')) {
      if (originals.has(element.id)) throw new Error('Duplicate drawing asset ID');
      originals.set(element.id, element);
    }
    const leaf = id => {
      const element = originals.get(id);
      if (!element || !['path', 'circle'].includes(element.localName)) throw new Error(`Missing drawing leaf ${id}`);
      return element;
    };
    this.palette = bindings.palette.map(id => {
      const element = leaf(id);
      const fill = element.getAttribute('fill'), stroke = element.getAttribute('stroke');
      if (![fill, stroke].every(value => /^#[0-9a-fA-F]{6}$/.test(value))) throw new Error('Unsupported drawing paint');
      const width = Number(element.getAttribute('stroke-width'));
      if (!(width > 0 && width <= 8)) throw new Error('Unsupported stroke width');
      return { fill, stroke, width };
    });
    this.root = document.createElementNS(SVG, 'g');
    this.root.setAttribute('data-opxy-display', 'cpp');
    // The device renderer only changes a fill the artwork already has.
    this.fillable = bindings.nodes.map(id => (leaf(id).getAttribute('fill') || 'none') !== 'none');
    this.nodes = bindings.nodes.map(id => {
      const original = leaf(id);
      const element = document.createElementNS(SVG, original.localName);
      // Never copy event handlers, links, styles or unknown XML attributes.
      for (const attribute of original.attributes) {
        if (attributeNames.has(attribute.name)) element.setAttribute(attribute.name, attribute.value);
      }
      return element;
    });
    // Preserve authored SVG paint order, independent of command/lookup order.
    for (const id of originals.keys()) {
      const index = bindings.nodes.indexOf(id);
      if (index >= 0) this.root.append(this.nodes[index]);
    }
    this.paths = bindings.paths.map(index => this.nodes[index]);
    if (this.paths.some(node => node.localName !== 'path')) throw new Error('Mutable asset must be a path');
    this.keys = paths.map(() => 0);
  }
  apply(frame) {
    if (!(frame instanceof Int32Array) || frame.length !== this.frameWords) throw new Error('Invalid drawing frame buffer');
    // Callers use PreviewDisplay, which runs the same native frame validator.
    const stride = 1 + 2 * this.points;
    for (let path = 0; path < this.paths.length; path++) {
      const offset = path * stride, key = frame[offset];
      if (this.keys[path] === key) continue;
      const segments = [];
      for (let i = 0; i < this.points; i++) {
        segments.push(`${i ? 'L' : 'M'}${decimal(frame[offset + 1 + i * 2])} ${decimal(frame[offset + 2 + i * 2])}`);
      }
      this.paths[path].setAttribute('d', segments.join(' ') + ' Z');
      this.keys[path] = key;
    }
    for (let i = 0; i < this.nodes.length; i++) {
      const offset = this.paths.length * stride + i * 5;
      const [x, y, scale, shade, paint] = frame.subarray(offset, offset + 5);
      const node = this.nodes[i];
      node.setAttribute('transform', `matrix(${decimal(scale)} 0 0 ${decimal(scale)} ${decimal(x)} ${decimal(y)})`);
      node.setAttribute('data-x', decimal(x));
      node.setAttribute('data-y', decimal(y));
      node.setAttribute('data-paint', String(paint));
      if (paint) {
        const palette = this.palette[shade];
        node.setAttribute('stroke', palette.stroke);
        node.setAttribute('stroke-width', String(palette.width));
        node.setAttribute('stroke-linejoin', 'round');
        if (paint === 2 && this.fillable[i]) node.setAttribute('fill', palette.fill);
      }
    }
  }
  svg() { return new XMLSerializer().serializeToString(this.root); }
}
