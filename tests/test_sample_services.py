"""Native qualification executes platform services with host boundary doubles."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from dataclasses import replace
from opxy_sdk.adapters import generate_sample_callbacks, generate_screen_order
from opxy_sdk.machines import machine

ROOT = Path(__file__).resolve().parents[1]


def host_compiler():
    """A C++ compiler that builds and runs host programs, or None."""
    compiler = os.environ.get('OPXY_TEST_HOST_CXX', 'g++')
    with tempfile.TemporaryDirectory(prefix='host-cxx-') as folder:
        source, binary = Path(folder) / 'probe.cpp', Path(folder) / ('probe.exe' if os.name == 'nt' else 'probe')
        source.write_text('int main() { return sizeof(unsigned) == 4 && sizeof(void*) >= 4 ? 0 : 1; }\n')
        hidden = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
        try:
            built = subprocess.run([compiler, str(source), '-o', str(binary)], capture_output=True, timeout=60, **hidden)
            return compiler if built.returncode == 0 and subprocess.run([str(binary)], timeout=30, **hidden).returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None


HOST_CXX = host_compiler()


@unittest.skipUnless(HOST_CXX, 'No working host C++ compiler (set OPXY_TEST_HOST_CXX)')
class SampleServices(unittest.TestCase):
    def run_fixture(self, name, extra=()):
        with tempfile.TemporaryDirectory(prefix='sample-services-') as folder:
            binary = Path(folder) / (name + ('.exe' if os.name == 'nt' else ''))
            hidden = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
            if name == 'sample_callbacks':
                probe = replace(machine('timestretch'), id='probe', identity=dict(engine=46, page=7))
                generate_sample_callbacks(folder, [probe])
            if name == 'screen_order':
                probe = replace(machine('fm2op'), id='probe', identity=dict(engine=46, page=112))
                generate_screen_order(folder, [probe, machine('timestretch'), machine('decimate')])
            command = [HOST_CXX, '-std=c++11', '-O2', '-Wall', '-Werror',
                       '-I' + str(folder), '-I' + str(ROOT / 'sdk/include'),
                       '-I' + str(ROOT / 'sdk/platform/opxy-1.2.0'), str(ROOT / 'tests/fixtures' / (name + '.cpp')),
                       *(str(ROOT / path) for path in extra), '-o', str(binary)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=120, **hidden)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120, **hidden)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cache_lifetime_capacity_and_browser_deferral(self):
        self.run_fixture('sample_cache')

    def test_progress_never_takes_over_another_notification(self):
        self.run_fixture('sample_progress', ('sdk/platform/opxy-1.2.0/sample_progress.cpp',))

    def test_saved_settings_tuning_and_trim_bounds(self):
        self.run_fixture('sample_region')

    def test_callbacks_work_for_another_engine_and_preserve_stock_fields(self):
        self.run_fixture('sample_callbacks')

    def test_owned_primary_screen_precedes_stock_overlays(self):
        self.run_fixture('screen_order')
