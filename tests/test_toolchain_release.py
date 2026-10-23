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


if __name__ == '__main__':
    unittest.main()
