"""Private-fixture package verifier attack tests; never write a device or original package.

The CLI's real independent compile is exercised by build/verify. These tests
cache that known-good compiler output and isolate the package comparison logic,
so each corruption need not launch the compiler again.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tooling import native
from tooling.formats import elf32, sha
from tooling.pipeline import document, read, save_json


@unittest.skipUnless(os.environ.get('OPXY_TEST_NATIVE_PACKAGE') and os.environ.get('OPXY_TEST_STOCK_OS') and
                     os.environ.get('OPXY_TEST_STOCK_CONTENT'), 'Private package and stock inputs not supplied')
class PackageVerification(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package = Path(os.environ['OPXY_TEST_NATIVE_PACKAGE']).resolve()
        cls.stock = read(Path(os.environ['OPXY_TEST_STOCK_OS']))
        cls.catalog = read(Path(os.environ['OPXY_TEST_STOCK_CONTENT']) / 'op1_factory.json')
        cls.module = read(cls.package / 'analysis/module.bin')
        cls.report = document(cls.package / 'analysis/compile-report.json')
        cls.elf = read(cls.package / 'analysis/module.elf')
        cls.patch_profile, cls.machines, _definitions = native.configuration()
        cls.patch_profile['patches'] = cls.report['patches']

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='opxy-tamper-')
        self.addCleanup(self.temporary.cleanup)
        self.copy = Path(self.temporary.name) / 'package'
        shutil.copytree(self.package, self.copy)

    def fresh_compile(self, directory, *_args):
        (directory / 'module.elf').write_bytes(self.elf)
        return self.module, copy.deepcopy(self.report), copy.deepcopy(self.patch_profile)

    def verify(self):
        with patch.object(native, 'compile_collection', self.fresh_compile):
            options = [Path('unused-mocked-toolchain')] * 2
            return native.verification(self.stock, self.catalog, self.copy, *options)

    def change_hash(self, name):
        manifest = document(self.copy / 'manifest.json')
        manifest['files'][name] = sha(read(self.copy / name))
        save_json(self.copy / 'manifest.json', manifest)

    def test_original_fixture_verifies(self):
        result = self.verify()
        self.assertTrue(result['fresh_source_rebuild_matches'])
        self.assertFalse(result['hardware_tested'])

    def test_only_curated_engines_are_linked_and_added_to_stock_content(self):
        _, symbols = elf32(self.elf)
        for m in self.machines:
            self.assertIn(m.prefix + ('_fx_factory' if m.kind == 'effect' else '_factory'), symbols)
        factories = {name for name in symbols if name.endswith('_factory')}
        self.assertEqual(factories, {m.prefix + ('_fx_factory' if m.kind == 'effect' else '_factory')
                                     for m in self.machines})
        original = json.loads(self.catalog)
        current = json.loads((self.package / 'candidate/content/op1_factory.json').read_bytes())
        names = [m.native_name for m in self.machines if m.kind != 'effect']
        self.assertEqual(current['engine_types'][:-len(names)], original['engine_types'])
        self.assertEqual([e['type'] for e in current['engine_types'][-len(names):]], names)
        displays = [m.native_name for m in self.machines if m.display != 'stock']
        files = {p.relative_to(self.package / 'candidate').as_posix()
                 for p in (self.package / 'candidate').rglob('*') if p.is_file()}
        self.assertEqual(files, {'os.ldr', 'content/op1_factory.json'} | {f'content/display/{n}.svg' for n in displays})

    def test_changed_os_elf_module_and_asset_fail_even_with_new_hash(self):
        names = ['candidate/os.ldr', 'analysis/module.elf', 'analysis/module.bin', 'candidate/content/op1_factory.json',
                 *(f'candidate/content/display/{m.native_name}.svg' for m in self.machines if m.display != 'stock')]
        for name in names:
            with self.subTest(name=name):
                path = self.copy / name
                original = path.read_bytes()
                changed = bytearray(original); changed[len(changed) // 2] ^= 1
                path.write_bytes(changed); self.change_hash(name)
                with self.assertRaises(ValueError): self.verify()
                path.write_bytes(original); self.change_hash(name)

    def test_false_hardware_and_native_provenance_fail(self):
        cases = (('verification.json', 'hardware_tested'),
                 ('analysis/compile-report.json', 'hardware_tested'))
        for name, key in cases:
            with self.subTest(name=name):
                path = self.copy / name; original = path.read_bytes()
                value = json.loads(original); value[key] = True; save_json(path, value)
                if name.startswith('analysis/'):
                    self.change_hash(name)
                with self.assertRaises(ValueError): self.verify()
                path.write_bytes(original)
                if name.startswith('analysis/'):
                    self.change_hash(name)

    def test_additional_deployment_file_and_manifest_escape_fail(self):
        (self.copy / 'candidate/bootloader.ldr').write_bytes(b'not deployment evidence')
        with self.assertRaises(ValueError): self.verify()
        (self.copy / 'candidate/bootloader.ldr').unlink()
        manifest = document(self.copy / 'manifest.json')
        manifest['files']['../outside'] = '0' * 64
        save_json(self.copy / 'manifest.json', manifest)
        with self.assertRaises(ValueError): self.verify()


if __name__ == '__main__':
    unittest.main()
