"""Relocated engine-record and screen-slot tables: profile, layout and templates.

No Blackfin code is compiled here. These checks keep the profile edits, the
linker layout and the generated registration consistent with the audited
constants in opxy_sdk/stock_tables.py.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from opxy_sdk import stock_tables as tables
from opxy_sdk.adapters import generate_registration
from opxy_sdk.machines import machine
from opxy_sdk.firmware import HOOKS

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'profiles/opxy-1.2.0.json'
LINKER = 'linker/opxy-1.2.0.ld'


def read_text(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


class Profile(unittest.TestCase):
    def setUp(self):
        self.profile = json.loads(read_text(PROFILE))
        self.profile['patches'] = self.profile['patches'][:7 + len(tables.EDITS)]  # sample dispatch and startup label follow tables

    def test_profile_is_base_plus_table_edits(self):
        tables.check_edits(self.profile['patches'])

    def test_edits_change_only_immediates_outside_hooks(self):
        for patch, (site, kind, stock, relocated) in zip(self.profile['patches'][7:], tables.EDITS):
            self.assertEqual(tables.decode(kind, bytes.fromhex(patch['before']))[1], stock)
            self.assertEqual(tables.decode(kind, bytes.fromhex(patch['after']))[1], relocated)
            self.assertNotIn(site, HOOKS)

    def test_altered_edit_is_rejected(self):
        for index, value in ((7, '02da4c8d64ff0000'), (14, 'f161'), (len(self.profile['patches']) - 1, '20e18100')):
            altered = copy.deepcopy(self.profile['patches'])
            altered[index]['after'] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                tables.check_edits(altered)
        with self.assertRaises(ValueError):
            tables.check_edits(self.profile['patches'][:-1])

    def test_imm7_bound_is_the_largest_encodable(self):
        self.assertEqual(tables.decode('imm7', bytes.fromhex('f961')), (0x6001, 63))
        self.assertEqual(tables.decode('imm7', bytes.fromhex('0962')), (0x6001, -63))


class Layout(unittest.TestCase):
    def test_linker_places_tables_at_audited_addresses(self):
        linker = read_text(LINKER)
        self.assertIn('__stock_screen_slots = %#x;' % tables.SCREEN_SLOTS, linker)
        self.assertIn('__stock_engine_records = %#x;' % tables.ENGINE_RECORDS, linker)
        self.assertIn('LENGTH = %#x' % (tables.SCREEN_SLOTS - 0x8d450d60), linker)
        self.assertEqual(tables.SCREEN_SLOTS + tables.SCREEN_COUNT * 4, tables.ENGINE_RECORDS)
        self.assertLessEqual(tables.ENGINE_RECORDS + tables.ENGINE_COUNT * tables.RECORD_BYTES,
                             tables.RESERVATION_END)

    def test_assignments_avoid_sentinels(self):
        tables.check_assignment(34, 82)
        for engine_id, page_id in ((33, 82), (34, 81), (63, 82), (34, 128), (0, 82), (34, 0)):
            with self.subTest(engine_id=engine_id, page_id=page_id), self.assertRaises(ValueError):
                tables.check_assignment(engine_id, page_id)


class Templates(unittest.TestCase):
    def generated(self, leaf):
        with tempfile.TemporaryDirectory() as directory:
            return generate_registration(directory, leaf, machine=machine('macroosc'), screen_bytes=320).read_text(encoding='utf-8')

    def test_expansion_names_only_relocated_tables(self):
        for leaf in ('register', 'readiness', 'screen_register'):
            text = self.generated(leaf)
            self.assertNotIn('%#x' % tables.STOCK_ENGINE_RECORDS, text)
            self.assertNotIn('%#x' % tables.STOCK_SCREEN_SLOTS, text)
            self.assertNotIn('= 81;', text)
        # The resolver's missing-name result stays the stock sentinel.
        self.assertIn('    R1 = 33;\n    CC = R0 == R1;', self.generated('register'))
        self.assertIn('    R3 = 33;\n    CC = R2 == R3;', self.generated('readiness'))


if __name__ == '__main__':
    unittest.main()
