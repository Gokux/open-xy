"""Toolchain release packaging: source coverage and PE import parsing, without binaries."""
import importlib.util
import json
from pathlib import Path, PurePosixPath
import struct
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'tools/gcc/package_release.py'
spec = importlib.util.spec_from_file_location('package_release', SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def tiny_pe(imports):
    """A minimal PE32+ image whose only section holds an import table."""
    section_rva, raw = 0x1000, 0x200
    names = b''.join(name.encode() + b'\0' for name in imports)
    table = len(imports) * 20 + 20
    descriptors, offset = b'', 0
    for name in imports:
        descriptors += struct.pack('<12xI4x', section_rva + table + offset)
        offset += len(name) + 1
    body = descriptors + bytes(20) + names
    image = bytearray(raw + len(body))
    image[:2] = b'MZ'
    struct.pack_into('<I', image, 0x3c, 0x40)
    image[0x40:0x44] = b'PE\0\0'
    struct.pack_into('<H12xH', image, 0x46, 1, 240)
    struct.pack_into('<H', image, 0x58, 0x20b)
    struct.pack_into('<I', image, 0x58 + 112 + 8, section_rva)
    struct.pack_into('<8xIIII', image, 0x58 + 240, len(body), section_rva, len(body), raw)
    image[raw:] = body
    return bytes(image)


def tiny_macho(libraries):
    """A minimal 64-bit Mach-O header with one LC_LOAD_DYLIB per library and an unrelated command."""
    commands = [struct.pack('<II', 0x19, 16) + bytes(8)]  # LC_SEGMENT_64 stand-in
    for name in libraries:
        text = name.encode() + b'\0'
        size = (24 + len(text) + 7) // 8 * 8
        commands.append(struct.pack('<IIIIII', 0xc, size, 24, 0, 0, 0) + text.ljust(size - 24, b'\0'))
    body = b''.join(commands)
    return struct.pack('<IiiIIIII', 0xfeedfacf, 0x0100000c, 0, 2, len(commands), len(body), 0, 0) + body


class ToolchainReleaseTests(unittest.TestCase):
    def test_every_pinned_library_has_a_source_package(self):
        manifest = json.loads((ROOT / 'tools/gcc/release-sources.json').read_text('utf-8'))
        pins = json.loads((ROOT / 'profiles/toolchains.json').read_text('utf-8'))
        for host, entry in manifest['hosts'].items():
            provided = {name for package in entry['runtime'] for name in package['provides']}
            libraries = {PurePosixPath(path).name for path in pins['hosts'][host]['compiler']
                         if path.endswith(('.dll', '.dylib'))}
            self.assertLessEqual(libraries, provided, host)
            for package in entry['runtime']:
                self.assertRegex(package['sha256'], '^[0-9a-f]{64}$')
                self.assertTrue(package['url'].endswith(package['file']))

    def test_pe_import_table(self):
        self.assertEqual(release.pe_imports(tiny_pe(['libgmp-10.dll', 'KERNEL32.dll'])),
                         ['libgmp-10.dll', 'KERNEL32.dll'])
        self.assertEqual(release.pe_imports(tiny_pe([])), [])
        with self.assertRaises(ValueError):
            release.pe_imports(b'ELF')

    def test_macho_load_commands(self):
        libraries = ['/usr/lib/libSystem.B.dylib', '/opt/homebrew/opt/gmp/lib/libgmp.10.dylib']
        self.assertEqual(release.macho_imports(tiny_macho(libraries)), libraries)
        with self.assertRaises(ValueError):
            release.macho_imports(tiny_pe([]))


if __name__ == '__main__':
    unittest.main()
