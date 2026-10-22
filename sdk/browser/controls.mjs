// Shared control/patch plumbing. Descriptors are validated by the SDK generator.
function freeze(value) {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}

export function physicalValue(mapping, value) {
  if (mapping.kind === 'enum') return Math.floor((Math.round(value * 0x7fffffff) >>> 16) * mapping.labels.length / 32768);
  if (mapping.kind === 'anchors') {
    const position = value * (mapping.values.length - 1);
    const i = Math.min(mapping.values.length - 2, Math.floor(position));
    return mapping.values[i] + (mapping.values[i + 1] - mapping.values[i]) * (position - i);
  }
  if (mapping.kind === 'power') return value ** mapping.exponent * mapping.maximum;
  if (mapping.kind === 'exponential') return mapping.minimum * (mapping.maximum / mapping.minimum) ** value;
  throw new Error('Unsupported parameter mapping');
}

// Screen views of the browser preview.
export const VIEWS = Object.freeze(['routing', 'waveform']);

export function createControls(input) {
  const descriptor = freeze(input);
  const parameters = descriptor.parameters;
  const definition = freeze({ id: descriptor.id, name: descriptor.name });
  const defaults = () => Object.fromEntries(parameters.map(p => [p.id, p.default]));
  function validateParameters(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        Object.keys(value).length !== parameters.length || parameters.some(p =>
          !Object.hasOwn(value, p.id) || !Number.isFinite(value[p.id]) || value[p.id] < 0 || value[p.id] > 1)) {
      throw new Error('Expected exactly the defined normalized controls between 0 and 1.');
    }
    return Object.fromEntries(parameters.map(p => [p.id, value[p.id]]));
  }
  const physical = value => Object.fromEntries(parameters.map(p => [p.id, physicalValue(p.mapping, value[p.id])]));
  function displayValue(id, value) {
    const parameter = parameters.find(p => p.id === id);
    if (!parameter) throw new Error('Unknown control');
    const v = physicalValue(parameter.mapping, value[id]);
    if (parameter.display === 'enum') return parameter.mapping.labels[v];
    if (parameter.display === 'ratio') return `${v.toFixed(3)}:1`;
    if (parameter.display === 'duration') return v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(2)} s`;
    return `${Math.round(value[id] * 100)}%`;
  }
  function q31(value) {
    validateParameters(value);
    return [...parameters.map(p => Math.round(value[p.id] * 0x7fffffff)), ...Array(8 - parameters.length).fill(0)];
  }
  function makePatch(value, view = VIEWS[0]) {
    if (!VIEWS.includes(view)) throw new Error('Unknown screen view.');
    return { kind: 'opxy-machine-preview', machine: definition.id,
      parameters: validateParameters(value), view, parametersQ31: q31(value) };
  }
  function readPatch(patch) {
    if (!patch || patch.kind !== 'opxy-machine-preview' || patch.machine !== definition.id) {
      throw new Error('This is not a supported engine preview patch.');
    }
    const canonical = makePatch(patch.parameters, patch.view);
    if (JSON.stringify(patch.parametersQ31) !== JSON.stringify(canonical.parametersQ31)) {
      throw new Error('Q31 values do not match the normalized controls.');
    }
    return canonical;
  }
  return Object.freeze({ definition, parameters, defaults, presets: descriptor.presets,
    physical, displayValue, q31, validateParameters, makePatch, readPatch });
}
