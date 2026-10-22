"""Send effects: generated adapters, catalog entries and startup calls."""
import json
from pathlib import Path
import tempfile
import unittest

from opxy_sdk import adapters
from opxy_sdk.machines import machine
from opxy_sdk.native import extend_catalog
from opxy_sdk.startup import render

ROOT = Path(__file__).resolve().parents[1]


def stock_like_catalog():
    return (b'{\n\t"engine_types": [\n        {\n            "type": "a",\n            "default_params": [0]\n        }\n    ],\n'
            b'\t"fx_types": [\n        {\n            "type": "delay",\n            "id": 0,\n'
            b'            "default_params": [1, 2, 3, 4, 0, 0, 0, 0]\n        }\n    ],\n\t"x": 1\n}\n')


class Generation(unittest.TestCase):
    def test_registration_names_only_fx_tables_and_routines(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_fx_registration(directory, machine('decimate')).read_text(encoding='utf-8')
        self.assertIn('    R1 = 0x846e9f58;', text)       # FX records
        self.assertIn('    P0 = 0x846e9f34;', text)       # FX name map
        self.assertIn('    P1 = 0x8d506054;', text)       # FX registrar
        self.assertEqual(text.count('    P1 = 0x8d506764;'), 2)  # FX resolver
        self.assertIn('    R1 = 19;\n    CC = R0 == R1;', text)
        for engine_only in ('0x846ea2e8', '0x846e9f4c', '0x8d505ecc', '0x8d506688', '[SP + 20]'):
            self.assertNotIn(engine_only, text)

    def test_object_adapter_fits_the_stock_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_fx_object(directory, machine('decimate')).read_text(encoding='utf-8')
        self.assertIn('static_assert(sizeof(State) <= opxy::effect_state_bytes', text)
        self.assertIn('static_assert(sizeof(Object) <= 480', text)
        self.assertIn('const void* const decimate_fx_vtable[8]', text)
        self.assertIn('{"rate", "mix"}', text)

    def test_catalog_entry_is_appended_to_fx_types_only(self):
        catalog = stock_like_catalog()
        ends = [catalog.index(b'\n    ]', catalog.index(key)) for key in (b'"engine_types"', b'"fx_types"')]
        profile = dict(stock_catalog_inserts=dict(zip(('engine_types', 'fx_types'), ends)))
        parsed = json.loads(extend_catalog(catalog, profile, [machine('decimate')]))
        self.assertEqual(parsed['fx_types'][-1], json.loads(adapters.catalog_entry(machine('decimate'))[1:]))
        self.assertEqual(parsed['engine_types'], json.loads(catalog)['engine_types'])
        self.assertEqual(extend_catalog(catalog, profile, []), catalog)

    def test_effects_register_before_the_role_check(self):
        text = render(['fm2op', 'macroosc'], ['decimate'])
        synth = text.split('extensions_synth_exit:')[1]
        self.assertLess(synth.index('CALL decimate_fx_register_checked;'), synth.index('P0 = 0x8d5c200c;'))
        self.assertIn('decimate_fx_page_id', synth)
        with self.assertRaises(ValueError):
            render(['fm2op'], ['fm2op'])


if __name__ == '__main__':
    unittest.main()
