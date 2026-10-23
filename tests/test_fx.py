"""Send effects: generated adapters and catalog entries."""
import json
import os
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from tooling import adapters
from tooling.machines import machine
from tooling.native import extend_catalog
from test_sample_services import HOST_CXX

ROOT = Path(__file__).resolve().parents[1]


def stock_like_catalog():
    return (b'{\n\t"engine_types": [\n        {\n            "type": "a",\n            "default_params": [0]\n        }\n    ],\n'
            b'\t"fx_types": [\n        {\n            "type": "delay",\n            "id": 0,\n'
            b'            "default_params": [1, 2, 3, 4, 0, 0, 0, 0]\n        }\n    ],\n\t"x": 1\n}\n')


class Generation(unittest.TestCase):
    def test_registration_describes_the_effect_record(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_registration(directory, machine('ringmod')).read_text(encoding='utf-8')
        self.assertIn('Record record = {ringmod_fx_factory, ringmod_fx_parameter_name, ringmod_fx_name, '
                      'ringmod_fx_id, ringmod_fx_page_id, 0};', text)
        self.assertIn('int ringmod_fx_register() { return sdk_register_effect(&record); }', text)
        for engine_only in ('sdk_register_engine', 'sdk_engine_ready', 'screen'):
            self.assertNotIn(engine_only, text)

    def test_object_adapter_fits_the_stock_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_fx_object(directory, machine('ringmod')).read_text(encoding='utf-8')
        self.assertIn('static_assert(sizeof(State) <= opxy::effect_state_bytes', text)
        self.assertIn('static_assert(sizeof(Object) <= 480', text)
        self.assertIn('const void* const ringmod_fx_vtable[8]', text)
        labels = ', '.join('"%s"' % p['label'].lower() for p in machine('ringmod').definition['parameters'])
        self.assertIn('{%s}' % labels, text)

    @unittest.skipUnless(HOST_CXX, 'No working host C++ compiler (set OPXY_TEST_HOST_CXX)')
    def test_stock_dry_query_uses_declared_slot_or_unity(self):
        # Execute the generated vtable with a trivial wet DSP. Only widen the
        # object header for the host; the native build retains the 4-byte check.
        for slot in (None, 0, 3, 7):
            with self.subTest(slot=slot), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                m = replace(machine('ringmod'), dry_parameter=slot)
                generated = adapters.generate_fx_object(folder, m)
                text = generated.read_text().replace('__builtin_offsetof(Object, state) == 4',
                                                     '__builtin_offsetof(Object, state) == sizeof(void*)')
                generated.write_text(text)
                (folder / 'fx.cpp').write_text('''#include <opxy/effect.hpp>
namespace ringmod {
struct State { unsigned initialized; };
void initialize(State& state) { state.initialized = 1; }
void process(State& state, opxy::Channel left, opxy::Channel right, opxy::Parameters) {
    if (state.initialized) { left[0] = 123; right[0] = -456; }
}
}
''')
                source = (ROOT / 'tests/fixtures/fx_object.cpp').read_text()
                (folder / 'test.cpp').write_text(source.replace('@SLOT@', str(-1 if slot is None else slot)))
                binary = folder / ('test.exe' if os.name == 'nt' else 'test')
                hidden = dict(creationflags=subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else {}
                command = [HOST_CXX, '-std=c++11', '-O2', '-Wall', '-Werror',
                           '-I' + str(ROOT / 'sdk/include'), str(folder / 'test.cpp'), '-o', str(binary)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=120, **hidden)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30, **hidden)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_catalog_entry_is_appended_to_fx_types_only(self):
        catalog = stock_like_catalog()
        ends = [catalog.index(b'\n    ]', catalog.index(key)) for key in (b'"engine_types"', b'"fx_types"')]
        profile = dict(stock_catalog_inserts=dict(zip(('engine_types', 'fx_types'), ends)))
        parsed = json.loads(extend_catalog(catalog, profile, [machine('ringmod')]))
        self.assertEqual(parsed['fx_types'][-1], json.loads(adapters.catalog_entry(machine('ringmod'))[1:]))
        self.assertEqual(parsed['engine_types'], json.loads(catalog)['engine_types'])
        self.assertEqual(extend_catalog(catalog, profile, []), catalog)


if __name__ == '__main__':
    unittest.main()
