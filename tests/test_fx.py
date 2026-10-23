"""Send effects: generated adapters and catalog entries."""
import json
import tempfile
import unittest

from opxy_sdk import adapters
from opxy_sdk.machines import machine
from opxy_sdk.native import extend_catalog


def stock_like_catalog():
    return (b'{\n\t"engine_types": [\n        {\n            "type": "a",\n            "default_params": [0]\n        }\n    ],\n'
            b'\t"fx_types": [\n        {\n            "type": "delay",\n            "id": 0,\n'
            b'            "default_params": [1, 2, 3, 4, 0, 0, 0, 0]\n        }\n    ],\n\t"x": 1\n}\n')


class Generation(unittest.TestCase):
    def test_registration_describes_the_effect_record(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_registration(directory, machine('decimate')).read_text(encoding='utf-8')
        self.assertIn('Record record = {decimate_fx_factory, decimate_fx_parameter_name, decimate_fx_name, '
                      'decimate_fx_id, decimate_fx_page_id, 0};', text)
        self.assertIn('int decimate_fx_register() { return sdk_register_effect(&record); }', text)
        for engine_only in ('sdk_register_engine', 'sdk_engine_ready', 'screen'):
            self.assertNotIn(engine_only, text)

    def test_object_adapter_fits_the_stock_slot(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_fx_object(directory, machine('decimate')).read_text(encoding='utf-8')
        self.assertIn('static_assert(sizeof(State) <= opxy::effect_state_bytes', text)
        self.assertIn('static_assert(sizeof(Object) <= 480', text)
        self.assertIn('const void* const decimate_fx_vtable[8]', text)
        labels = ', '.join('"%s"' % p['label'].lower() for p in machine('decimate').definition['parameters'])
        self.assertIn('{%s}' % labels, text)

    def test_catalog_entry_is_appended_to_fx_types_only(self):
        catalog = stock_like_catalog()
        ends = [catalog.index(b'\n    ]', catalog.index(key)) for key in (b'"engine_types"', b'"fx_types"')]
        profile = dict(stock_catalog_inserts=dict(zip(('engine_types', 'fx_types'), ends)))
        parsed = json.loads(extend_catalog(catalog, profile, [machine('decimate')]))
        self.assertEqual(parsed['fx_types'][-1], json.loads(adapters.catalog_entry(machine('decimate'))[1:]))
        self.assertEqual(parsed['engine_types'], json.loads(catalog)['engine_types'])
        self.assertEqual(extend_catalog(catalog, profile, []), catalog)


if __name__ == '__main__':
    unittest.main()
