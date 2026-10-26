import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tooling import catalog, cpu_measurement
from tooling.benchmark import cases
from tooling.profile_report import aggregate, create, package_data
from tooling.formats import sha
from machine_fixtures import fixture
from test_catalog import PUBLISHED, document


def measurement(kind='synth', commit=None):
    return dict(benchmark=cpu_measurement.BENCHMARKS[kind], commit=commit or PUBLISHED['commit'],
                firmware_sha256='a' * 64, runs=3, block_percent=4.81,
                report='https://github.com/someone/machine/issues/1#issuecomment-123')


class Measurements(unittest.TestCase):
    def test_report_binds_clean_committed_sources_and_omits_device_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            machine_root = root / 'machine'
            machine_root.mkdir()
            catalog.git('init', cwd=machine_root)
            source = machine_root / 'engine.cpp'
            source.write_text('// committed machine source\n')
            catalog.git('add', 'engine.cpp', cwd=machine_root)
            catalog.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                        '-c', 'commit.gpgsign=false', 'commit', '-m', 'Fixture', cwd=machine_root)
            commit = catalog.git('rev-parse', 'HEAD', cwd=machine_root).strip()
            machine = SimpleNamespace(id='probesynth', root=machine_root,
                                      files=lambda: {'external/probesynth/engine.cpp': source})
            expected = cases([fixture('probesynth')])
            package = root / 'package'
            (package / 'candidate').mkdir(parents=True)
            (package / 'analysis').mkdir()
            # No firmware fixture is needed to exercise the offline report contract.
            firmware = b'non-firmware test placeholder'
            (package / 'candidate/os.ldr').write_bytes(firmware)
            report = dict(profiling=True, benchmark_cases=expected,
                          sources={'external/probesynth/engine.cpp': sha(source.read_bytes())})
            report_bytes = json.dumps(report).encode()
            (package / 'analysis/compile-report.json').write_bytes(report_bytes)
            (package / 'manifest.json').write_text(json.dumps(dict(profiling=True, files={
                'candidate/os.ldr': sha(firmware), 'analysis/compile-report.json': sha(report_bytes)})))
            _, _, identity = package_data(package)
            frames = [dict(command=0x94, route=0x12,
                           payload_hex=(struct.pack('>HHH', 3000, 1000, 1451)*20).hex()) for _ in expected]
            paths = []
            for index in range(3):
                path = root / f'run-{index}.json'
                path.write_text(json.dumps(dict(mode='benchmark', package=identity, expected_cases=expected,
                    complete=True, errors=[], collector_sha256='d'*64, frames=frames, utc=str(index),
                    identity={'serial': 'PRIVATE-SERIAL'})))
                paths.append(path)
            with patch('tooling.native.package_collection', return_value=[]), \
                 patch('tooling.native.package_layout', return_value=None), \
                 patch('tooling.native.configuration', return_value=(None, [machine], None)):
                output = create(package, paths, 'probesynth', measurement()['report'], root / 'report')
                published = json.loads((output / 'catalog-cpu.json').read_text())['cpu']
                self.assertEqual(published['commit'], commit)
                self.assertNotIn('PRIVATE-SERIAL', (output / 'report.md').read_text())
                source.write_text('// changed after measurement\n')
                with self.assertRaisesRegex(ValueError, 'Commit the machine'):
                    create(package, paths, 'probesynth', measurement()['report'], root / 'dirty')
                catalog.git('add', 'engine.cpp', cwd=machine_root)
                catalog.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                            '-c', 'commit.gpgsign=false', 'commit', '-m', 'Changed', cwd=machine_root)
                with self.assertRaisesRegex(ValueError, 'differs from the measured build'):
                    create(package, paths, 'probesynth', measurement()['report'], root / 'stale')

    def test_all_kinds_and_stale_or_invalid_measurements(self):
        for kind in cpu_measurement.BENCHMARKS:
            entry = dict(PUBLISHED, kind=kind, cpu=measurement(kind))
            catalog.validate(document(entry))
            for change in ({'commit': 'b'*40}, {'runs': True}, {'runs': 2}, {'block_percent': float('nan')},
                           {'block_percent': 0}, {'block_percent': 100}, {'block_percent': True},
                           {'report': 'javascript:alert(1)'}, {'report': 'https://user:pass@example.com/x'},
                           {'firmware_sha256': 'x'}, {'benchmark': 'host-estimate'}):
                with self.subTest(kind=kind, change=change), self.assertRaises(ValueError):
                    catalog.validate(document(dict(entry, cpu=dict(entry['cpu'], **change))))

    def test_changed_submissions_require_a_measurement_but_legacy_entries_can_stay(self):
        for kind in cpu_measurement.BENCHMARKS:
            entry = dict(PUBLISHED, kind=kind)
            catalog.changes([entry], [entry])
            for before, after in (([], [entry]), ([entry], [dict(entry, tag='v2')])):
                with self.assertRaisesRegex(ValueError, 'require hardware'):
                    catalog.changes(before, after)
            measured = dict(entry, cpu=measurement(kind))
            catalog.changes([entry], [measured])
            with self.assertRaisesRegex(ValueError, 'catalog commit'):
                catalog.changes([measured], [dict(measured, commit='b'*40)])
            catalog.changes([entry], [dict(entry, status='retired')])

    def test_report_rejects_repeated_wrong_build_incomplete_or_inactive_runs(self):
        expected = cases([fixture('probesynth'), fixture('probefx'), fixture('probesample')])
        identity = dict(firmware_sha256='a'*64, manifest_sha256='b'*64, compile_report_sha256='c'*64)
        frames = [dict(command=0x94, route=0x12,
                       payload_hex=(struct.pack('>HHH', 3000, 1000, 1451)*20).hex()) for _ in expected]
        captures = [dict(mode='benchmark', package=identity, expected_cases=expected, complete=True,
                         errors=[], collector_sha256='d'*64, frames=frames, utc=str(i)) for i in range(3)]
        for name, kind in (('probesynth', 'synth'), ('probefx', 'effect'), ('probesample', 'sample')):
            result, values, case = aggregate(captures, expected, identity, name, 'e'*40, measurement()['report'])
            self.assertEqual(result['benchmark'], cpu_measurement.BENCHMARKS[kind])
            self.assertAlmostEqual(result['block_percent'], 100000/65535, places=5)
        broken = [captures[:2], [captures[0]]*3,
                  [dict(captures[0], package={}), *captures[1:]],
                  [dict(captures[0], errors=['CRC']), *captures[1:]],
                  [dict(captures[0], complete=False), *captures[1:]],
                  [dict(captures[0], frames=frames[:-1]), *captures[1:]]]
        silent = copy.deepcopy(captures)
        silent[0]['frames'][-1]['payload_hex'] = '00' * 120
        broken.append(silent)
        for data in broken:
            with self.assertRaises(ValueError):
                aggregate(data, expected, identity, 'probesample', 'e'*40, measurement()['report'])
