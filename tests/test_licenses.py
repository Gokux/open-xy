"""Copyleft code stays inside the machine that uses it."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SHARED = ('sdk', 'opxy_sdk', 'builder', 'tools', 'linker', 'profiles', 'harness')


class Licenses(unittest.TestCase):
    def test_shared_code_carries_no_copyleft_notice(self):
        # Shared code is linked into every selection, so a copyleft file there
        # would bind every build; machine folders are linked only when selected.
        found = [path.relative_to(ROOT).as_posix() for folder in SHARED for path in (ROOT / folder).rglob('*')
                 if path.is_file() and path.suffix in ('.c', '.cc', '.cpp', '.h', '.hpp', '.in', '.s', '.py', '.mjs', '.js')
                 and 'SPDX-License-Identifier: AGPL' in path.read_text(encoding='utf-8', errors='replace')]
        self.assertEqual(found, [])


if __name__ == '__main__':
    unittest.main()
