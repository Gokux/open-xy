"""Enum controls step one choice per detent, show their label, and a declared press selects the next choice."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

from tooling.adapters import generate_synth_controls
from tooling.definitions import validate_definition
from tooling.formats import ldr, mapped_offset
from tooling.machines import machine_at
from tooling.pipeline import ROOT, config
from test_sample_services import HOST_CXX
from machine_fixtures import FOLDER, fixture

STOCK_OS = os.environ.get('OPXY_TEST_STOCK_OS')


def enum(identifier, count, **extra):
    return dict(id=identifier, label=identifier, default=0, display='enum',
                mapping=dict(kind='enum', labels=['c%d' % i for i in range(count)]), **extra)


class SynthSteps(unittest.TestCase):
    def synth(self, *parameters):
        definition = copy.deepcopy(fixture('probesynth').definition)
        definition['parameters'][:len(parameters)] = parameters
        definition['presets'] = {}
        return definition

    def test_table_lists_enum_steps_and_presses(self):
        definition = self.synth(enum('mode', 3, press='next'), *fixture('probesynth').definition['parameters'][1:2],
                                enum('scene', 17), enum('wide', 256))
        validate_definition(definition, 'synth')
        machines = [SimpleNamespace(kind='synth', prefix='steps', identity=dict(engine=40), definition=definition)]
        with tempfile.TemporaryDirectory() as directory:
            text = generate_synth_controls(directory, machines).read_text(encoding='utf-8')
        row = re.search(r'^    \{steps_engine_id, steps_ready, \{[\d, ]+\}, (\d+), \{([\d, ]+)\}, (\d+),', text, re.M)
        # Stock steps at most 255 buckets, so the 256-choice enum stays with stock.
        self.assertEqual(row.group(2), '3, 0, 17, 0, 0, 0, 0, 0')
        self.assertEqual(row.group(3), '1')
        # Every enum's value text is its selected label, including the one stock steps.
        self.assertIn('static const char* const labels[] = {"c0", "c1", "c2"};', text)
        self.assertIn('control_label(text, value, labels, 3);', text)
        self.assertIn('control_label(text, value, labels, 17);', text)
        self.assertIn('control_label(text, value, labels, 256);', text)

    def test_press_is_a_next_choice_on_a_position_without_alternates(self):
        base = fixture('probesynth').definition['parameters']
        validate_definition(self.synth(enum('mode', 3, press='next')), 'synth')
        rejected = [
            self.synth(dict(base[0], press='next')),                 # not an enum
            self.synth(enum('mode', 3, press='cycle')),              # unknown press
            self.synth(enum('mode', 256, press='next')),             # beyond stock's steps
        ]
        alternate = self.synth(enum('mode', 3, press='next'))
        alternate['parameters'].append(dict(enum('other', 2), control=0))
        rejected.append(alternate)                                    # presses cycle its alternates
        on_alternate = self.synth(enum('mode', 3))
        on_alternate['parameters'].append(dict(enum('other', 2, press='next'), control=1))
        rejected.append(on_alternate)
        for bad in rejected:
            with self.subTest(parameters=[p.get('press') for p in bad['parameters']]), self.assertRaises(ValueError):
                validate_definition(bad, 'synth')
        effect = copy.deepcopy(fixture('probefx').definition)
        effect['parameters'][0] = enum('mode', 3, press='next')
        with self.assertRaisesRegex(ValueError, 'parameter fields'):
            validate_definition(effect, 'effect')

    def test_press_needs_sdk_1_2(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / 'probesynth'
            shutil.copytree(FOLDER / 'probesynth', folder)
            (folder / 'definition.json').write_text(json.dumps(self.synth(enum('mode', 3, press='next'))))
            record = json.loads((folder / 'machine.json').read_text())
            for version, accepted in (('1.1', False), ('1.2', True)):
                (folder / 'machine.json').write_text(json.dumps(dict(record, sdk=version)))
                with self.subTest(version=version):
                    if accepted:
                        self.assertEqual(machine_at(folder).id, 'probesynth')
                    else:
                        with self.assertRaisesRegex(ValueError, 'press'):
                            machine_at(folder)

    def test_hook_replaces_the_step_count_call(self):
        hooks = [p for p in config()['patches'] if p.get('symbol') == 'sdk_param_steps']
        self.assertEqual(len(hooks), 1)
        hook = hooks[0]
        self.assertEqual((int(hook['address'], 16), hook['length'], hook['call']), (0x8d5ab636, 8, True))
        # CALL.A 0x8c0b2fc8, the step-count query of stock's encoder step 8d5ab618.
        self.assertEqual(hook['before'], '00de0b8cc82f0000')
        self.assertNotIn('service', hook)

    @unittest.skipUnless(STOCK_OS, 'Set OPXY_TEST_STOCK_OS to the stock os.ldr')
    def test_hook_bytes_match_the_stock_os(self):
        data = Path(STOCK_OS).read_bytes()
        hook = next(p for p in config()['patches'] if p.get('symbol') == 'sdk_param_steps')
        offset = int(hook['file_offset'], 16)
        self.assertEqual(mapped_offset(ldr(data), int(hook['address'], 16), hook['length']), offset)
        self.assertEqual(data[offset:offset + hook['length']].hex(), hook['before'])

    @unittest.skipUnless(HOST_CXX, 'No working host C++ compiler (set OPXY_TEST_HOST_CXX)')
    def test_real_platform_adapter(self):
        platform = ROOT / 'sdk/platform/opxy-1.2.0'
        with tempfile.TemporaryDirectory(prefix='synth-steps-') as directory:
            folder = Path(directory)
            # Substitute only the stock-address boundary, as other SDK fixtures do.
            stock = (platform / 'stock.hpp').read_text(encoding='utf-8')
            stock = stock.replace('typedef __UINTPTR_TYPE__ Address;',
                                  'typedef __UINTPTR_TYPE__ Address;\nAddress host_stock_address(Address);')
            for pointer in ('T*', 'const volatile u32*', 'const volatile unsigned char*'):
                stock = stock.replace('reinterpret_cast<' + pointer + '>(address)',
                                      'reinterpret_cast<' + pointer + '>(host_stock_address(address))')
            (folder / 'stock.hpp').write_text(stock, encoding='utf-8')
            (folder / 'synth_controls.cpp').write_bytes((platform / 'synth_controls.cpp').read_bytes())
            binary = folder / ('test.exe' if os.name == 'nt' else 'test')
            hidden = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
            result = subprocess.run([HOST_CXX, '-std=c++11', '-O2', '-Wall', '-Werror',
                '-I' + str(folder), '-I' + str(ROOT / 'sdk/include'), '-I' + str(platform),
                str(ROOT / 'tests/fixtures/synth_steps.cpp'), '-o', str(binary)],
                capture_output=True, text=True, timeout=120, **hidden)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30, **hidden)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
