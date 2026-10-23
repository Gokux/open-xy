import re
import unittest
import tempfile
from pathlib import Path
from opxy_sdk.adapters import generate_voice

from opxy_sdk.contributors import validate_source_boundary
from opxy_sdk.machines import discovered, machine
from opxy_sdk.native import check_sources


class ContributorBoundary(unittest.TestCase):
    def test_voice_adapter_includes_only_the_machine_and_sdk(self):
        with tempfile.TemporaryDirectory() as directory:
            source = generate_voice(directory, machine('fm2op')).read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'#include "([^"]+)"', source), ['core.h', 'engine.cpp', 'stock.hpp'])
        self.assertIn('fm2op::render(slot->voice, shared, owner(slot), output, parameters, increments);', source)

    def test_machines_have_no_platform_branches(self):
        check_sources(discovered())

    def test_platform_specific_code_is_rejected(self):
        for source in ('#ifdef _WIN32\n#endif', '#if 1\n#endif',
                       '#include <windows.h>', '#include "io.h"',
                       '__asm__("RTS;");', 'bool x = __bfin__;'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_source_boundary(source)

    def test_portable_example_and_explanatory_comments_are_allowed(self):
        validate_source_boundary('''#pragma once
#include "opxy/q31.hpp"
// The SDK owns #ifdef _WIN32 and __asm__.
/* Never include <windows.h> in an instrument. */
opxy::i32 sample(opxy::i32 x) { return opxy::q31::half(x); }
''')


if __name__ == '__main__':
    unittest.main()
