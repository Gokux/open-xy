"""Strict schema for a machine's definition.json, shared by every kind."""
import math
from pathlib import Path
import re

from .formats import require

ROOT = Path(__file__).resolve().parents[1]


def keys(value, expected, label):
    require(isinstance(value, dict) and set(value) == set(expected), 'Unexpected ' + label + ' fields')


def number(value, low, high, label):
    require(type(value) in (int, float) and low <= value <= high and math.isfinite(value),
            'Invalid ' + label)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', value), 'Invalid identifier')


# The stock firmware's own engine and effect types (stock 1.2.0 catalog).
STOCK_TYPES = frozenset({'sampler', 'drum', 'drumline', 'organ', 'epiano', 'prism', 'hardsync', 'dissolve', 'axis',
                         'wavetable', 'simple', 'midi', 'multisampler',
                         'delay', 'reverb', 'chorus', 'phaser', 'dist', 'lofi'})
# Symbol namespaces the SDK and firmware glue use; a machine's name prefixes its symbols.
RESERVED_PREFIXES = ('extensions', 'sdk', 'kit', 'stock', 'local')


def stock_name(value):
    """A machine's name: its folder, stock engine type, preset and screen file, and symbol prefix."""
    require(isinstance(value, str) and re.fullmatch(r'[a-z][a-z0-9_]{0,14}', value),
            'Machine names are a lowercase letter, then letters, digits or _, at most 15 characters')
    require(value not in STOCK_TYPES, 'Machine name is a stock engine or effect type: ' + value)
    require(not any(value == p or value.startswith(p + '_') for p in RESERVED_PREFIXES),
            'Machine name uses a reserved symbol prefix: ' + value)


def label(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 _-]{0,63}', value),
            'Labels must be short plain text')


def control_label(value):
    # The stock parameter page shows control names in lower case, at most eight characters.
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ]{0,7}', value),
            'Control labels are at most eight letters, digits or spaces')


# Resources each kind declares; the SDK owns everything else about its storage.
RESOURCES = {
    'synth': ('voiceBytes', 'voiceAlignment', 'voiceCapacity', 'sharedBytes', 'blockFrames', 'sampleRate',
              'outputPeakQ31', 'display'),
    'sample': ('voiceCapacity',),
    'effect': (),
}
# A synth's own screen: the machine declares its shape within these limits.
DISPLAY_FIELDS = {
    'drawing': ('kind', 'stateBytes', 'stateAlignment', 'paths', 'points', 'nodes', 'palette'),
    'segments': ('kind', 'characters', 'glow', 'dials', 'textControls'),
}
DRAWING_LIMITS = dict(paths=(1, 4), points=(2, 64), nodes=(1, 64), palette=(1, 16))
SEGMENT_CHARACTERS = (1, 8)
SEGMENT_GLOW = (0, 3)
SEGMENT_DIALS = (0, 4)
# Analysis storage is allocated from the stock heap at runtime, which also holds
# stock samples; the SDK lets one machine take at most this much of it.
ANALYSIS_HEAP_LIMIT = 2 * 1024 * 1024
# Synths fill the four-control page; sample engines and effects use up to the
# stock eight-word parameter vector.
CONTROLS = {'synth': (4, 4), 'sample': (1, 8), 'effect': (1, 8)}


def validate_definition(value, kind):
    keys(value, ('schema', 'id', 'name', 'parameters', 'presets', 'cppNamespace', 'resources'), 'definition')
    require(type(value['schema']) is int and value['schema'] == 1, 'Unknown definition schema')
    stock_name(value['id']); label(value['name'])
    require(isinstance(value['cppNamespace'], str) and
            re.fullmatch(r'[a-z][a-z0-9_]{0,31}', value['cppNamespace']), 'Invalid C++ namespace')
    resources = value['resources']
    optional = tuple(k for k in ('sampleAnalysis', 'chokeSameKey', 'drumControls', 'stereoOutput') if kind == 'sample' and isinstance(resources, dict) and k in resources)
    keys(resources, (*RESOURCES[kind], *optional), 'resources')
    require(all(type(v) is int for k, v in resources.items() if k != 'display'),
            'Numeric resource requirements must be integers')
    if 'voiceCapacity' in resources:
        require(1 <= resources['voiceCapacity'] <= 256, 'Voice capacity must be 1..256')
    if kind == 'sample':
        heap = resources.get('sampleAnalysis', 0)
        require(type(heap) is int and (heap == 0 or (4096 <= heap <= ANALYSIS_HEAP_LIMIT and heap % 4 == 0)),
                'sampleAnalysis is 0 or the analysis heap budget in bytes, up to %d' % ANALYSIS_HEAP_LIMIT)
        require(resources.get('chokeSameKey', 0) in (0, 1), 'Same-key choke must be 0 or 1')
        require(resources.get('drumControls', 0) in (0, 1), 'Drum controls must be 0 or 1')
        require(resources.get('stereoOutput', 0) in (0, 1), 'Stereo output must be 0 or 1')
    if kind == 'synth':
        validate_synth_resources(resources)
    parameters = value['parameters']
    low, high = CONTROLS[kind]
    require(isinstance(parameters, list) and low <= len(parameters) <= high,
            f'Control count outside {low}..{high} for this kind')
    names = set()
    for parameter in parameters:
        validate_parameter(parameter)
        require(parameter['id'] not in names, 'Duplicate parameter identity')
        names.add(parameter['id'])
    require(isinstance(value['presets'], dict) and len(value['presets']) <= 64, 'Invalid presets')
    for name, preset in value['presets'].items():
        label(name); keys(preset, names, 'preset')
        for default in preset.values(): number(default, 0, 1, 'preset value')
    return value


def validate_synth_resources(resources):
    # Sizes are bounded by the shared module memory, checked when the collection links.
    require(4 <= resources['voiceBytes'] and resources['voiceBytes'] % 4 == 0,
            'Voice state must occupy at least one whole word')
    require(resources['voiceAlignment'] in (4, 8, 16) and
            resources['voiceBytes'] % resources['voiceAlignment'] == 0, 'Unsupported voice alignment')
    require(0 <= resources['sharedBytes'] and resources['sharedBytes'] % 4 == 0,
            'Shared state must occupy whole words')
    require(resources['blockFrames'] == 64 and resources['sampleRate'] == 44100,
            'Unsupported stock audio contract')
    require(0 < resources['outputPeakQ31'] <= 0x7fffffff, 'Invalid oscillator output headroom')
    validate_display(resources['display'])


def validate_display(display):
    require(isinstance(display, dict) and isinstance(display.get('kind'), str) and display['kind'] in DISPLAY_FIELDS,
            'Unknown display kind')
    keys(display, DISPLAY_FIELDS[display['kind']], 'display')
    if display['kind'] == 'drawing':
        for name, (low, high) in DRAWING_LIMITS.items():
            require(type(display[name]) is int and low <= display[name] <= high,
                    'Drawing %s must be %d..%d' % (name, low, high))
        require(display['paths'] <= display['nodes'], 'Each path is also a node')
        require(type(display['stateBytes']) is int and type(display['stateAlignment']) is int and
                4 <= display['stateBytes'] and display['stateAlignment'] in (4, 8, 16) and
                display['stateBytes'] % display['stateAlignment'] == 0,
                'Display state must occupy aligned whole words')
    else:
        low, high = SEGMENT_CHARACTERS
        require(type(display['characters']) is int and low <= display['characters'] <= high,
                'Segment displays have %d..%d characters' % (low, high))
        for name, (low, high) in (('glow', SEGMENT_GLOW), ('dials', SEGMENT_DIALS)):
            require(type(display[name]) is int and low <= display[name] <= high,
                    'Segment display %s must be %d..%d' % (name, low, high))
        controls = display['textControls']
        require(isinstance(controls, list) and all(type(c) is int and 0 <= c < 4 for c in controls) and
                controls == sorted(set(controls)), 'textControls lists distinct control indices 0..3 in order')


def validate_parameter(parameter):
    keys(parameter, ('id', 'label', 'default', 'mapping', 'display'), 'parameter')
    identifier(parameter['id']); control_label(parameter['label'])
    number(parameter['default'], 0, 1, 'normalized default')
    require(parameter['display'] in ('ratio', 'percent', 'duration', 'enum'), 'Unsupported display format')
    mapping = parameter['mapping']
    require(isinstance(mapping, dict), 'Invalid mapping')
    kind = mapping.get('kind')
    require((parameter['display'] == 'enum') == (kind == 'enum'), 'Enum mapping/display must agree')
    if kind == 'enum':
        keys(mapping, ('kind', 'labels'), 'enum mapping')
        labels = mapping['labels']
        require(isinstance(labels, list) and 2 <= len(labels) <= 256 and
                all(isinstance(s, str) and re.fullmatch(r'[A-Za-z0-9 *+_-]{1,15}', s) for s in labels) and
                len(set(labels)) == len(labels) and parameter['display'] == 'enum', 'Invalid enum labels')
    elif kind == 'anchors':
        keys(mapping, ('kind', 'values'), 'anchor mapping')
        anchors = mapping['values']
        require(isinstance(anchors, list) and 2 <= len(anchors) <= 256, 'Invalid anchor count')
        for anchor in anchors: number(anchor, -1e9, 1e9, 'anchor')
        require(all(a < b for a, b in zip(anchors, anchors[1:])), 'Anchors must increase')
    elif kind == 'power':
        keys(mapping, ('kind', 'maximum', 'exponent'), 'power mapping')
        number(mapping['maximum'], 0, 1e9, 'mapping maximum')
        number(mapping['exponent'], 0.01, 32, 'mapping exponent')
    elif kind == 'exponential':
        keys(mapping, ('kind', 'minimum', 'maximum'), 'exponential mapping')
        number(mapping['minimum'], 1e-9, 1e9, 'mapping minimum')
        number(mapping['maximum'], mapping['minimum'], 1e9, 'mapping maximum')
    else:
        raise ValueError('Unsupported mapping kind')
