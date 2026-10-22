"""Generated startup continuations for any number of curated engines."""
import re
import unittest

from opxy_sdk.startup import MAX_ENGINES, render


def calls(text):
    return re.findall(r'(?:CALL|JUMP\.L) (\w+);', text)


class Startup(unittest.TestCase):
    def test_each_engine_registers_on_both_paths_in_ledger_order(self):
        text = render(['fm2op', 'macroosc', 'third'])
        synth, rest = text.split('.Lsynth_done:')
        screen, catalog = rest.split('extensions_catalog_checked:')
        self.assertEqual([c for c in calls(synth) if c.endswith('_draft')],
                         ['fm2op_register_checked_draft', 'macroosc_register_checked_draft', 'third_register_checked_draft'])
        self.assertEqual([c for c in calls(screen) if c.endswith('screen_register_checked')],
                         ['fm2op_screen_register_checked', 'macroosc_screen_register_checked', 'third_screen_register_checked'])
        # A failed page guard skips only that engine's GUI-side registration.
        self.assertIn('    IF !CC JUMP .Lscreen_macroosc;', screen)
        self.assertIn('    IF !CC JUMP .Lscreen_done;', screen)
        self.assertEqual(screen.count('    CALL third_register_checked_draft;'), 1)

    def test_first_engine_delegates_and_others_route_by_name(self):
        catalog = render(['fm2op', 'macroosc', 'third']).split('extensions_catalog_checked:')[1]
        self.assertEqual([c for c in calls(catalog) if c.endswith('_name_matches')],
                         ['third_name_matches', 'macroosc_name_matches'])
        self.assertEqual([c for c in calls(catalog) if c.endswith('_catalog_checked')],
                         ['fm2op_catalog_checked', 'third_catalog_checked', 'macroosc_catalog_checked'])
        self.assertNotIn('fm2op_name_matches', catalog)

    def test_single_engine_has_no_routes(self):
        text = render(['fm2op'])
        self.assertNotIn('_name_matches', text)
        self.assertIn('    JUMP.L fm2op_catalog_checked;', text)

    def test_rejects_invalid_engine_lists(self):
        for prefixes in ([], ['fm2op', 'fm2op'], ['Bad'], ['x%d' % i for i in range(MAX_ENGINES + 1)]):
            with self.subTest(prefixes=prefixes[:3]), self.assertRaises(ValueError):
                render(prefixes)


if __name__ == '__main__':
    unittest.main()
