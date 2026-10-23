"""Relocated engine-record and screen-slot tables: profile, layout and templates.

No Blackfin code is compiled here. These checks keep the profile edits, the
linker layout and the stock side of registration consistent with the audited
constants in opxy_sdk/stock_tables.py.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from opxy_sdk import stock_tables as tables
from opxy_sdk.adapters import generate_registration_stock
from opxy_sdk.firmware import hooks
from opxy_sdk.pipeline import config

ROOT = Path(__file__).resolve().parents[1]
PROFILE = 'profiles/opxy-1.2.0.json'
LINKER = 'linker/opxy-1.2.0.ld'


def read_text(relative):
    return (ROOT / relative).read_text(encoding='utf-8')


class Profile(unittest.TestCase):
    def setUp(self):
        self.profile = config()
        self.table = [p for p in self.profile['patches'] if p['kind'] == 'table']

    def test_profile_agrees_with_the_audit(self):
        tables.check_profile(self.profile)

    def test_edits_change_only_immediates_outside_hooks(self):
        for patch, (site, kind, stock, relocated) in zip(self.table, tables.EDITS):
            self.assertEqual(tables.decode(kind, bytes.fromhex(patch['before']))[1], stock)
            self.assertEqual(tables.decode(kind, bytes.fromhex(patch['after']))[1], relocated)
            self.assertNotIn(site, hooks(self.profile))

    def test_altered_edit_or_bound_is_rejected(self):
        for index, value in ((0, '02da4c8d64ff0000'), (7, 'f161'), (len(self.table) - 1, '20e18100')):
            altered = copy.deepcopy(self.table)
            altered[index]['after'] = value
            with self.subTest(index=index), self.assertRaises(ValueError):
                tables.check_edits(altered)
        with self.assertRaises(ValueError):
            tables.check_edits(self.table[:-1])
        for key, value in (('engines', 64), ('engine_none', 32), ('pages', 127), ('page_none', 80)):
            altered = copy.deepcopy(self.profile)
            altered['identities'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                tables.check_profile(altered)
        with self.assertRaises(ValueError):
            tables.check_profile(dict(self.profile, table_bytes=self.profile['table_bytes'] + 4))

    def test_compositor_bound_must_be_hooked(self):
        hooked = [p for p in self.profile['patches'] if p['kind'] == 'hook']
        tables.check_compositor(hooked)
        site = '%#x' % tables.COMPOSITOR_ADVANCE
        for change in (dict(symbol='sdk_other'), dict(before='0f6420e180008708'), dict(address='0x8d5208fc')):
            altered = copy.deepcopy(hooked)
            next(p for p in altered if p['address'] == site).update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                tables.check_compositor(altered)

    def test_imm7_bound_is_the_largest_encodable(self):
        self.assertEqual(tables.decode('imm7', bytes.fromhex('f961')), (0x6001, 63))
        self.assertEqual(tables.decode('imm7', bytes.fromhex('0962')), (0x6001, -63))


class Layout(unittest.TestCase):
    def test_linker_places_tables_at_audited_addresses(self):
        linker = read_text(LINKER)
        self.assertIn('__stock_screen_slots = %#x;' % tables.SCREEN_SLOTS, linker)
        self.assertIn('__stock_engine_records = %#x;' % tables.ENGINE_RECORDS, linker)
        self.assertIn('LENGTH = %#x' % (tables.SCREEN_SLOTS - config()['module_base']), linker)
        self.assertEqual(tables.SCREEN_SLOTS + tables.SCREEN_COUNT * 4, tables.ENGINE_RECORDS)
        self.assertLessEqual(tables.ENGINE_RECORDS + tables.ENGINE_COUNT * tables.RECORD_BYTES,
                             tables.RESERVATION_END)


class Registration(unittest.TestCase):
    def test_stock_side_names_only_relocated_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            text = generate_registration_stock(directory).read_text(encoding='utf-8')
        self.assertIn('const Registry kEngines = {%#x, %d, %d,' % (tables.ENGINE_RECORDS, tables.ENGINE_COUNT,
                                                                     tables.ENGINE_SENTINEL), text)
        self.assertIn('const Pages kPages = {%d,' % tables.SCREEN_COUNT, text)
        self.assertIn('%#x' % tables.SCREEN_SLOTS, text)
        self.assertNotIn('%#x' % tables.STOCK_ENGINE_RECORDS, text)
        self.assertNotIn('%#x' % tables.STOCK_SCREEN_SLOTS, text)


if __name__ == '__main__':
    unittest.main()
