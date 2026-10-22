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
from opxy_sdk import sample_hooks
from opxy_sdk.startup import render

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'sdk/platform/opxy-1.2.0'


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

    def test_gui_exceptions_authenticate_all_interval_fields(self):
        for address, (_, before, offset) in sample_hooks.EDITS.items():
            patch = dict(address=hex(address), before=before, length=len(bytes.fromhex(before)), file_offset=hex(offset))
            self.assertTrue(sample_hooks.allowed({'id': 'opxy-1.2.0'}, patch))
            self.assertFalse(sample_hooks.allowed({'id': 'other'}, patch))
            for key, value in [('address', hex(address + 2)), ('before', '00' + before[2:]),
                               ('length', patch['length'] + 2), ('file_offset', hex(offset + 2))]:
                if value == patch[key]: value = 'ff' + before[2:]
                with self.subTest(address=hex(address), key=key):
                    self.assertFalse(sample_hooks.allowed({'id': 'opxy-1.2.0'}, dict(patch, **{key: value})))

    def test_absolute_calls_reject_invalid_width_opcode_padding_and_alignment(self):
        for target in (0, 0x8d450d60, 0xfffffffe):
            self.assertEqual(sample_hooks.absolute_target(sample_hooks.absolute_call(target)), target)
        for target in (-2, 1, 0x100000000):
            with self.assertRaises(ValueError): sample_hooks.absolute_call(target)
        valid = sample_hooks.absolute_call(0x8d450d60)
        for bad in (valid[:-1], valid + b'\0', b'\1' + valid[1:], valid[:4] + b'\x61' + valid[5:], valid[:-1] + b'\1'):
            with self.assertRaises(ValueError): sample_hooks.absolute_target(bad)

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

    def test_registration_stores_and_checks_flag_one(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_sample_registration(directory, machine('timestretch'), 'register').read_text(encoding='utf-8')
        self.assertIn('    R0 = 1;\n    [SP + 16] = R0;', text)
        self.assertIn('    R0 = [P4 + 8];\n    R1 = 1;\n    CC = R0 == R1;', text)
        self.assertIn('    R2 = 63;', text)            # relocated engine limit
        self.assertIn('    R1 = 0x8d4cff60;', text)    # relocated engine records

    def test_stock_page_readiness_drops_only_the_own_page_checks(self):
        own = (TEMPLATES / 'readiness.s.in').read_text(encoding='utf-8')
        stock = (TEMPLATES / 'readiness_stock_page.s.in').read_text(encoding='utf-8')
        for gone in ('0x84ebbf84', '@SCREEN_SLOTS@', '_screen_state', '_screen_vtable', '_screen_asset'):
            self.assertIn(gone, own)
            self.assertNotIn(gone, stock)
        for kept in ('@PREFIX@_name_matches:', '@PREFIX@_catalog_checked:', 'CALL @PREFIX@_record_owned_draft;',
                     '    R3 = 33;\n    CC = R2 == R3;', 'JUMP.L stock_catalog_insert;'):
            self.assertIn(kept, stock)

    def test_voice_adapter_validates_the_stock_sample_object(self):
        with tempfile.TemporaryDirectory() as directory:
            text = adapters.generate_sample_voice(directory, machine('timestretch')).read_text(encoding='utf-8')
        self.assertIn('0x8404fb1c', text)
        self.assertIn('frames >= (1u << 20)', text)
        self.assertIn('opxy::audio_bpm_x10', text)
        self.assertIn('0x84c710d4', text)
        self.assertNotIn('0x8409d2c8', text)
        self.assertIn('static Slot voices[256];', text)

    def test_catalog_entry_and_stock_page_startup(self):
        entry = json.loads(adapters.catalog_entry(machine('timestretch')).strip().lstrip(','))
        self.assertEqual(entry['type'], 'timestretch')
        screen = render(['fm2op', 'macroosc', 'timestretch'], (), ['timestretch']).split('extensions_screen_exit:')[1]
        self.assertNotIn('timestretch_screen_register_checked', screen)
        self.assertIn('.Lscreen_timestretch:\n    R0.H = timestretch_engine_id;', screen)


if __name__ == '__main__':
    unittest.main()
