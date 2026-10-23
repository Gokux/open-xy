import argparse
import tempfile
from pathlib import Path
import unittest

from opxy_sdk.checks import FIXTURES, fixture_environment, run_suite
from unittest.mock import patch


class CheckRunnerTests(unittest.TestCase):
    def options(self, **values):
        return argparse.Namespace(**{key: values.get(key) for key in (*FIXTURES, 'toolchain')})

    def test_public_mode_does_not_silently_use_stale_private_fixtures(self):
        env, native = fixture_environment(self.options(), {'PATH': 'retained', 'OPXY_TEST_NATIVE_ELF': 'stale'})
        self.assertEqual(env, {'PATH': 'retained'})
        self.assertFalse(native)

    def test_partial_native_inputs_fail_instead_of_falling_back_to_public(self):
        with self.assertRaises(ValueError):
            fixture_environment(self.options(native_package=Path('missing')), {})

    def test_native_inputs_must_exist_and_bind_elf_to_package(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            values = {}
            for key, (_env, relative) in FIXTURES.items():
                values[key] = root / key
                file = values[key] / relative if relative else values[key]
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'fixture')
            values['toolchain'] = root / 'tools'
            values['toolchain'].mkdir()
            env, native = fixture_environment(self.options(**values), {})
            self.assertTrue(native)
            # Hosted Windows runners can expose TEMP through an 8.3 alias.
            self.assertEqual(Path(env['OPXY_TEST_NATIVE_ELF']),
                             (values['native_package'] / 'analysis/module.elf').resolve())
            values['stock_os'].unlink()
            with self.assertRaises(ValueError):
                fixture_environment(self.options(**values), {})

    def test_native_suite_rejects_skipped_test_even_when_unittest_succeeds(self):
        with patch('opxy_sdk.checks.unittest.TestLoader.discover'), patch('builtins.print'), \
             patch('opxy_sdk.checks.unittest.TextTestRunner') as runner:
            result = runner.return_value.run.return_value
            result.wasSuccessful.return_value = True
            result.skipped = [('case', 'missing input')]
            self.assertEqual(run_suite(require_all=True), 1)
            self.assertEqual(run_suite(require_all=False), 0)
