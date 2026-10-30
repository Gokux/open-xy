"""Revision-bound hardware measurements required for changed catalog submissions."""
import math
import re

from .formats import require

BENCHMARKS = {'synth': 'opxy-synth-c8-v1', 'effect': 'opxy-effect-callback-v1',
              'sample': 'opxy-sample-callback-v1'}
FIELDS = {'benchmark', 'commit', 'firmware_sha256', 'runs', 'block_percent'}
# A synth may instead submit the control sweep staging's profiling builds measure:
# block_percent its heaviest run, midpoint_percent stock's midpoint run,
# combined_percent every control at its heaviest position, and worst_setting the
# heaviest single swept setting.
SWEEP = 'opxy-synth-c8-sweep-v1'
SWEEP_FIELDS = FIELDS | {'midpoint_percent', 'combined_percent', 'worst_setting'}
# An optional public evidence URL, never a local path or a URL with credentials.
REPORT_URL = r'https://[A-Za-z0-9.-]+(?::[0-9]+)?/[^\s<>"\\]*'


def validate(value, kind, commit=None):
    """A measurement's fields; with a commit, also that it measured that commit."""
    require(isinstance(value, dict), 'cpu: unexpected measurement fields')
    allowed = {BENCHMARKS.get(kind)} | ({SWEEP} if kind == 'synth' else set())
    require(kind in BENCHMARKS and value.get('benchmark') in allowed, 'cpu: benchmark must match the machine kind')
    sweep = value['benchmark'] == SWEEP
    require(set(value) - {'report'} == (SWEEP_FIELDS if sweep else FIELDS), 'cpu: unexpected measurement fields')
    require(isinstance(value['commit'], str) and re.fullmatch(r'[0-9a-f]{40}', value['commit']),
            'cpu: commit is the full SHA of the measured machine source')
    require(commit is None or value['commit'] == commit, 'cpu: measurement must match the catalog commit')
    require(isinstance(value['firmware_sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', value['firmware_sha256']),
            'cpu: firmware_sha256 must identify the measured build')
    require(type(value['runs']) is int and 3 <= value['runs'] <= 100, 'cpu: use 3 to 100 independent runs')
    for field in ('block_percent', 'midpoint_percent', 'combined_percent') if sweep else ('block_percent',):
        number = value[field]
        require(type(number) in (int, float) and math.isfinite(number) and 0 < number < 100,
                f'cpu: {field} must be an unsaturated, positive percentage of the stock block budget')
    if sweep:
        setting = value['worst_setting']
        require(isinstance(setting, dict) and set(setting) - {'option'} == {'control', 'label', 'value'} and
                type(setting['control']) is int and 0 <= setting['control'] < 8 and
                isinstance(setting['label'], str) and 0 < len(setting['label']) <= 32 and
                type(setting['value']) is int and 0 <= setting['value'] <= 0x7fffffff and
                ('option' not in setting or isinstance(setting['option'], str) and 0 < len(setting['option']) <= 32),
                'cpu: worst_setting names the heaviest control, its label and Q31 value '
                '(and a list control\'s option)')
        require(max(value['midpoint_percent'], value['combined_percent']) <= value['block_percent'],
                'cpu: block_percent is the heaviest run, the midpoint and combined runs included')
    if 'report' in value:
        require(isinstance(value['report'], str) and len(value['report']) <= 2048 and
                re.fullmatch(REPORT_URL, value['report']), 'cpu: report must be a public HTTPS evidence URL')
    return value
