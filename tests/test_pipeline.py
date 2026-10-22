"""Public tests use synthetic containers; private integration fixtures are opt-in."""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from opxy_sdk.formats import elf32, header, ldr, mapped_offset, sha
from opxy_sdk import pipeline
from opxy_sdk.pipeline import ROOT, PROTECTED, check_patch_boundaries, child, config, fresh_output


class Formats(unittest.TestCase):
    def fixture(self):
        return header(4, 0x1000, 4, 0) + b'abcd' + header(0x8004, 0x1000, 0, 0)

    def test_stored_mapping(self):
        blocks = ldr(self.fixture())
        self.assertEqual(mapped_offset(blocks, 0x1001, 2), 17)
        with self.assertRaises(ValueError):
            mapped_offset(blocks, 0x1003, 2)

    def test_header_checksum(self):
        bad = bytearray(self.fixture())
        bad[4] ^= 1
        with self.assertRaises(ValueError):
            ldr(bad)

    def test_truncation_suffix_and_missing_final(self):
        for data in (self.fixture()[:-1], self.fixture() + b'\0', self.fixture()[:20], b''):
            with self.subTest(data_length=len(data)), self.assertRaises(ValueError):
                ldr(data)

    def test_fill_is_not_stored_and_overlap_rejected(self):
        data = header(0x104, 0x1000, 16, 0) + self.fixture()
        with self.assertRaises(ValueError):
            mapped_offset(ldr(data), 0x1000, 4)
        data = header(0x104, 0x2000, 16, 0) + self.fixture()
        with self.assertRaises(ValueError):
            mapped_offset(ldr(data), 0x2000, 4)

    def test_address_overflow(self):
        with self.assertRaises(ValueError):
            ldr(header(0x104, 0xfffffff0, 32, 0) + self.fixture())

    def test_malformed_elf_rejected(self):
        for data in (b'', b'\x7fELF\x01\x01' + bytes(60)):
            with self.assertRaises(ValueError):
                elf32(data)


class SourceContracts(unittest.TestCase):
    def test_sdk_layout_is_pinned_and_keeps_reservation(self):
        profile = config()
        self.assertEqual(profile['module_base'], 0x8d450d60)
        self.assertEqual(profile['reserved_bytes'], 0x80000)
        self.assertEqual(sha((ROOT / 'linker/opxy-1.2.0.ld').read_bytes()), profile['linker_sha256'])

    def test_patch_intervals_do_not_overlap(self):
        profile = config()
        self.assertEqual(len(profile['patches']), 48)
        seen = set()
        for patch in profile['patches']:
            before, after = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
            self.assertEqual(len(before), len(after))
            self.assertNotEqual(before, after)
            positions = set(range(int(patch['address'], 16), int(patch['address'], 16) + len(before)))
            self.assertFalse(seen & positions)
            seen.update(positions)

    def test_protected_ranges_reject_profile_edits(self):
        profile = config()
        for start, end in PROTECTED:
            with self.subTest(address=hex(start)):
                altered = copy.deepcopy(profile)
                altered['patches'][0]['address'] = hex(start)
                with self.assertRaises(ValueError):
                    check_patch_boundaries(altered, 48)
        altered = copy.deepcopy(profile)
        altered['patches'][1] = copy.deepcopy(altered['patches'][0])
        with self.assertRaises(ValueError):
            check_patch_boundaries(altered, 48)

    def test_path_escape_and_absolute_paths_rejected(self):
        for name in ('../os.ldr', '/os.ldr', 'C:/os.ldr', 'a/../../x', 'a\\x', 'a//x', './x', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                child(ROOT, name)

    def test_output_never_overwrites(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'existing'
            path.mkdir()
            (path / 'keep.txt').write_text('keep')
            with self.assertRaises(ValueError):
                fresh_output(path)
            self.assertEqual((path / 'keep.txt').read_text(), 'keep')

    def test_release_host_has_tools_and_compiler(self):
        pins = pipeline.toolchains()
        release = pins['hosts'][pins['release']]
        self.assertTrue(release['tools'] and release['compiler'])
        for drop in ('compiler', 'executable_suffix'):
            broken = copy.deepcopy(pins)
            del broken['hosts'][pins['release']][drop]
            with self.subTest(drop=drop), self.assertRaises(ValueError):
                pipeline.check_toolchains(broken)
        with mock.patch.object(pipeline, 'read', return_value=b'{}'), self.assertRaises(ValueError):
            pipeline.toolchains()

    def test_msys_python_is_a_windows_host(self):
        for system in ('MSYS_NT-10.0-26200', 'CYGWIN_NT-10.0', 'MINGW64_NT-10.0'):
            with self.subTest(system=system), mock.patch('platform.system', return_value=system),                     mock.patch('platform.machine', return_value='x86_64'):
                self.assertEqual(pipeline.host_platform(), 'windows-x86_64')

    def test_release_kits_only_on_release_host(self):
        release = pipeline.toolchains()['release']
        with mock.patch.object(pipeline, 'host_platform', return_value=release):
            pipeline.require_release_host()
        with mock.patch.object(pipeline, 'host_platform', return_value='other-host'),                 self.assertRaisesRegex(ValueError, 'on ' + release + ', not other-host'):
            pipeline.require_release_host()


if __name__ == '__main__':
    unittest.main()
