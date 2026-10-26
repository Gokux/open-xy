"""Diagnostic collection generation, ABI forwarding and strict report attribution."""
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch
import struct
import tempfile
import unittest

from tooling.benchmark import cases, decode, generate
from machine_fixtures import fixture
from tooling.pipeline import config
from tooling.firmware import decode_branch


class Benchmark(unittest.TestCase):
    def test_wire_codec_matches_retrieved_device_requests(self):
        from tools import benchmark as transport
        transport.selftest()
        self.assertEqual(transport.frame(0x21, 5, 0).hex(), 'f000207621660002210205020c00f7')
        self.assertEqual(transport.frame(0x21, 9, 1).hex(), 'f000207621660004210109027300f7')
        self.assertEqual(transport.frame(0x21, 0xc8, 2).hex(), 'f000207621660804210248024900f7')

    def test_arbitrary_synth_and_non_synth_exclusion(self):
        synth = replace(fixture('probesynth'), id='unfamiliar', identity=dict(engine=46, page=91))
        selected = [fixture('probefx'), synth, fixture('probesample')]
        self.assertEqual(cases(selected)[9:], [dict(name='unfamiliar', engine=46, source='sdk')])
        with tempfile.TemporaryDirectory() as folder:
            source = generate(folder, selected).read_text(encoding='utf-8')
            self.assertIn('unfamiliar_ready', source)
            self.assertNotIn('probesynth', source)
            self.assertNotIn('probefx', source)
            self.assertNotIn('probesample', source)
            empty = generate(folder, []).read_text(encoding='utf-8')
            self.assertIn('{0, 0, 0}', empty)

    def test_hook_replaces_only_the_explicit_diagnostic_runner(self):
        patch = next(p for p in config()['patches'] if p.get('symbol') == 'sdk_benchmark_run')
        self.assertEqual(decode_branch(int(patch['address'], 16), bytes.fromhex(patch['before'])),
                         (0x8d57bc64, True))
        self.assertEqual(patch['length'], 4)

    def test_reports_refuse_missing_extra_corrupt_or_wrong_endpoint_data(self):
        expected = cases([fixture('probesynth')])
        frame = dict(command=0x94, route=0x12, payload_hex=(struct.pack('>HHH', 65535, 1000, 300) * 20).hex())
        capture = dict(complete=True, errors=[], frames=[frame] * len(expected))
        result = decode(capture, expected)
        self.assertEqual(result[-1]['machine']['name'], 'probesynth')
        self.assertTrue(result[-1]['metrics'][3]['maximum_clipped'])
        self.assertAlmostEqual(result[-1]['metrics'][3]['average_budget_percent'], 100000 / 65535)
        for change in [dict(complete=False), dict(errors=['CRC']), dict(frames=capture['frames'][:-1]),
                       dict(frames=capture['frames'] + [frame]),
                       dict(frames=[dict(frame, route=0x15)] * len(expected)),
                       dict(frames=[dict(frame, payload_hex='00')] * len(expected))]:
            with self.assertRaises(ValueError):
                decode(dict(capture, **change), expected)

    def test_collector_rejects_disabled_or_missing_profiling_before_device_access(self):
        from tools import benchmark as transport
        with tempfile.TemporaryDirectory() as folder:
            package = Path(folder)
            for value in (False, None, 1, 'on'):
                (package / 'manifest.json').write_text(json.dumps(dict(profiling=value)))
                with patch('sys.argv', ['benchmark.py', 'benchmark', '--package', str(package),
                                        '--out', str(package / 'capture')]):
                    with self.assertRaisesRegex(ValueError, 'profiling-enabled'):
                        transport.main()
                self.assertFalse((package / 'capture').exists())
