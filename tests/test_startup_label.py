import copy
import json
import unittest

from tooling import startup_label as label
from tooling.pipeline import ROOT, check_patch_boundaries


class StartupLabelTests(unittest.TestCase):
    def test_label_edit_is_exactly_the_reviewed_one(self):
        profile = json.loads((ROOT / f'profiles/{label.PROFILE}.json').read_text())
        count = len(profile['patches'])
        check_patch_boundaries(profile, count)
        edit = profile['patches'][-1]
        self.assertTrue(label.allowed(profile, edit))
        for key, value in [('address', hex(label.SITE + 2)), ('before', '00' * 10),
                           ('length', 8), ('file_offset', '0xf04d6'), ('symbol', 'other')]:
            changed = copy.deepcopy(profile)
            changed['patches'][-1][key] = value
            with self.assertRaises(ValueError):
                check_patch_boundaries(changed, count)
        profile['id'] = 'another-profile'
        with self.assertRaises(ValueError):
            check_patch_boundaries(profile, count)

    def test_absolute_hook_rejects_wrong_opcodes_padding_and_width(self):
        for address in (0x8d450d60, 0x8d4cfd5e):
            self.assertEqual(label.destination(label.jump(address)), address)
        for address in (-1, 1, 0x100000000):
            with self.assertRaises(ValueError):
                label.jump(address)
        valid = label.jump(0x8d450d60)
        for data in (valid[:8], valid + b'\0', b'\0' * 10):
            with self.assertRaises(ValueError):
                label.destination(data)
        for index in (0, 1, 4, 6, 7, 8, 9):
            changed = bytearray(valid)
            changed[index] ^= 1
            with self.assertRaises(ValueError):
                label.destination(changed)


if __name__ == '__main__':
    unittest.main()
