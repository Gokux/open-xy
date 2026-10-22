"""Sample-playback engines: flag-1 registration, stock-page readiness and startup."""
import json
import copy
from pathlib import Path
import tempfile
import unittest
from dataclasses import replace

from opxy_sdk import adapters
from opxy_sdk.machines import machine
from opxy_sdk.definitions import validate_definition
from opxy_sdk import firmware
from opxy_sdk.startup import render

ROOT = Path(__file__).resolve().parents[1]


class Generation(unittest.TestCase):
    def test_optional_services_are_explicit_integer_flags(self):
        definition = copy.deepcopy(machine('timestretch').definition)
        for key in ('sampleAnalysis', 'chokeSameKey', 'drumControls', 'stereoOutput'):
            for value in (True, -1, 2, '1', None):
                invalid = copy.deepcopy(definition)
                invalid['resources'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_definition(invalid, 'sample')
        for value in (1, 4092, 4097, 2 * 1024 * 1024 + 4):
            invalid = copy.deepcopy(definition)
            invalid['resources']['sampleAnalysis'] = value
            with self.subTest(heap=value), self.assertRaises(ValueError):
                validate_definition(invalid, 'sample')
        definition['resources'] = {'voiceCapacity': 256}
        validate_definition(definition, 'sample')

    def test_absolute_calls_reject_invalid_width_opcode_padding_and_alignment(self):
        for target in (0, 0x8d450d60, 0xfffffffe):
            self.assertEqual(firmware.absolute_target(firmware.absolute_call(target)), target)
        for target in (-2, 1, 0x100000000):
            with self.assertRaises(ValueError): firmware.absolute_call(target)
        valid = firmware.absolute_call(0x8d450d60)
        for bad in (valid[:-1], valid + b'\0', b'\1' + valid[1:], valid[:4] + b'\x61' + valid[5:], valid[:-1] + b'\1'):
            with self.assertRaises(ValueError): firmware.absolute_target(bad)

    def test_routes_are_generated_for_arbitrary_sample_identities(self):
        first = machine('timestretch')
        second = replace(first, id='slicer', identity=dict(engine=46, page=7))
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_sample_routes(directory, [first, second, machine('fm2op')]).read_text()
        self.assertIn('R1 = 35;', text)
        self.assertIn('R1 = 46;', text)
        self.assertIn('CALL timestretch_ready;', text)
        self.assertIn('CALL slicer_ready;', text)
        self.assertNotIn('fm2op_ready', text)
        self.assertEqual(text.count('IF !CC JUMP .Lkind_return;'), 2)
        self.assertIn('    R0 = 7;', text)

    def test_empty_collection_routes_remain_stock(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_sample_routes(directory, []).read_text()
        self.assertIn('extensions_sample_kind:\n    LINK 12;\n\n    R0 = 0;', text)
        self.assertNotIn('_ready;', text)

    def test_engine_units_expand_every_placeholder(self):
        m = replace(machine('timestretch'), identity=dict(engine=46, page=2))
        with tempfile.TemporaryDirectory() as directory:
            for leaf in ('register', 'readiness_stock_page'):
                text = adapters.generate_sample_registration(directory, m, leaf).read_text(encoding='utf-8')
                self.assertNotIn('@', text, leaf)
            self.assertNotIn('@', adapters.generate_sample_voice(directory, m).read_text(encoding='utf-8'))

    def test_catalog_entry_and_stock_page_startup(self):
        entry = json.loads(adapters.catalog_entry(machine('timestretch')).strip().lstrip(','))
        self.assertEqual(entry['type'], 'timestretch')
        screen = render(['fm2op', 'macroosc', 'timestretch'], (), ['timestretch']).split('extensions_screen_exit:')[1]
        self.assertNotIn('timestretch_screen_register_checked', screen)
        self.assertIn('.Lscreen_timestretch:\n    R0.H = timestretch_engine_id;', screen)


if __name__ == '__main__':
    unittest.main()
