"""Audio-callback call graph: recursion fails, stack bounds follow the deepest path."""
from types import SimpleNamespace
import unittest

from tooling.native import audio_stack_bounds

BASE = 0x1000


def disassembly(functions):
    lines = []
    address = BASE + 0x100
    for name, body in functions:
        lines.append(f'{address:08x} <{name}>:')
        for text in body:
            lines.append(f'{address:08x}:\t00 00 \t{text}')
            address += 2
    return '\n'.join(lines)


def image(entry):
    module = bytearray(0x100)
    module[0x08:0x0c] = entry.to_bytes(4, 'little')  # method table slot +8 at BASE
    return bytes(module)


SYMBOLS = {'_m_vtable': dict(value=BASE, size=44, type=1)}
MACHINE = [SimpleNamespace(id='m', kind='synth', prefix='m')]


class AudioStack(unittest.TestCase):
    def test_bound_is_the_deepest_direct_path(self):
        text = disassembly([('render', ['LINK 0x10;', f'CALL 0x{BASE + 0x108:x} <leaf>;', 'UNLINK;', 'RTS;']),
                            ('leaf', ['[--SP] = R7;', 'R7 = [SP++];', 'RTS;'])])
        self.assertEqual(audio_stack_bounds(text, image(BASE + 0x100), BASE, SYMBOLS, MACHINE), {'m': 0x18 + 4})

    def test_recursion_fails(self):
        text = disassembly([('render', ['LINK 0x0;', f'CALL 0x{BASE + 0x100:x} <render>;', 'RTS;'])])
        with self.assertRaisesRegex(ValueError, 'Recursive'):
            audio_stack_bounds(text, image(BASE + 0x100), BASE, SYMBOLS, MACHINE)


if __name__ == '__main__':
    unittest.main()
