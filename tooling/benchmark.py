"""Generate the diagnostic synth list from the same collection as the firmware."""
from pathlib import Path
import struct

from .pipeline import ROOT
from .formats import require

STOCK = [('prism', 18), ('simple', 32), ('hardsync', 19), ('dissolve', 20),
         ('axis', 22), ('organ', 6), ('epiano', 7), ('wavetable', 31), ('chord', 13)]


def cases(machines):
    return [dict(name=name, engine=engine, source='stock') for name, engine in STOCK] + [
        dict(name=m.id, engine=m.identity['engine'], source='sdk')
        for m in machines if m.kind == 'synth']


def generate(directory, machines):
    synths = [m for m in machines if m.kind == 'synth']
    declarations, rows = [], []
    for m in synths:
        p = m.prefix
        declarations += [f'int {p}_ready() __asm__("{p}_ready");',
                         f'extern const char {p}_engine_id[] __asm__("{p}_engine_id");']
        rows.append(f'    {{"{m.id}", {p}_engine_id, {p}_ready}},')
    source = (ROOT / 'sdk/platform/opxy-1.2.0/benchmark.cpp.in').read_text(encoding='utf-8')
    source = source.replace('@DECLARATIONS@', '\n'.join(declarations))
    source = source.replace('@MACHINES@', '\n'.join(rows))
    path = Path(directory) / 'benchmark.cpp'
    path.write_text(source, encoding='utf-8', newline='\n')
    return path


def decode(capture, expected):
    """Attribute only a complete ordered run; packets carry no machine identity."""
    frames = [f for f in capture['frames'] if f['command'] == 0x94]
    require(capture['complete'] and not capture['errors'], 'Incomplete or corrupt capture')
    require(len(frames) == len(expected), 'Report count differs from this build; refusing machine attribution')
    require(all(f['route'] == 0x12 and len(bytes.fromhex(f['payload_hex'])) == 120 for f in frames),
            'Unexpected report endpoint or size')
    scale = struct.unpack('<f', bytes.fromhex('1844e73d'))[0]
    result = []
    for case, frame in zip(expected, frames):
        payload = bytes.fromhex(frame['payload_hex'])
        metrics = []
        for index in range(20):
            maximum, average, accumulated = struct.unpack_from('>HHH', payload, index * 6)
            metrics.append(dict(index=index, encoded_maximum=maximum, encoded_average=average,
                                encoded_accumulated=accumulated, maximum_clipped=maximum == 65535,
                                average_budget_percent=100 * average / 65535,
                                approximate_average_cycles=average / scale))
        result.append(dict(machine=case, metrics=metrics,
                           insufficient_voice_activity=metrics[3]['encoded_accumulated'] < 10))
    return result
