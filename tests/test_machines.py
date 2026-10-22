"""machine.json: kinds, displays and the stock identity each machine declares."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from opxy_sdk import machines
from opxy_sdk.pipeline import config

RULES = config()['identities']


def identity(kind, **changes):
    value = {'synth': dict(engine=34, page=82), 'sample': dict(engine=35, page=2),
             'effect': dict(effect=11, page=21)}[kind]
    return dict(value, **changes)


class Identity(unittest.TestCase):
    def test_bundled_machines_declare_valid_identities(self):
        # Every bundled machine is valid and part of the collection, in its declared order.
        listed = json.loads(machines.COLLECTION.read_text(encoding='utf-8'))['machines']
        self.assertEqual({m.id for m in machines.discovered()}, set(listed))
        self.assertEqual([m.id for m in machines.collection()], listed)

    def test_stock_occupied_or_sentinel_ids_are_rejected(self):
        for kind, change in (('synth', dict(engine=33)), ('synth', dict(engine=2)), ('synth', dict(engine=63)),
                             ('synth', dict(page=81)), ('synth', dict(page=128)), ('synth', dict(engine=True)),
                             ('sample', dict(engine=26)), ('sample', dict(page=82)),
                             ('effect', dict(effect=0)), ('effect', dict(effect=5)), ('effect', dict(page=20))):
            with self.subTest(kind=kind, change=change), self.assertRaises(ValueError):
                machines.check_identity(RULES, kind, identity(kind, **change))

    def test_own_screen_pages_come_from_the_relocated_range(self):
        machines.check_identity(RULES, 'synth', identity('synth'))
        for page in (2, 21, 50, 81):
            with self.subTest(page=page), self.assertRaises(ValueError):
                machines.check_identity(RULES, 'synth', identity('synth', page=page))

    def test_names_and_fields_are_checked(self):
        # The folder name is the stock name, so identity holds only IDs.
        for kind, value in (('synth', identity('synth', name='probe')), ('synth', identity('synth', prefix='probe')),
                            ('effect', dict(identity('effect'), engine=34))):
            with self.subTest(value=value), self.assertRaises(ValueError):
                machines.check_identity(RULES, kind, value)
        for name in ('a' * 16, 'Bad', 'two-op', '', 'drum', 'reverb', 'sdk', 'kit_probe', 'extensions'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                machines.machine(name)
        self.assertEqual((machines.machine('fm2op').native_name, machines.machine('fm2op').prefix), ('fm2op', 'fm2op'))
        with self.assertRaises(ValueError):
            machines.machine('2opfm')

    def test_collection_rejects_conflicting_identities(self):
        original = machines.machine

        def clash(name):
            m = original(name)
            return m if name != 'timestretch' else machines.Machine(**dict(m.__dict__, identity=dict(engine=34, page=2)))
        with mock.patch.object(machines, 'machine', clash), self.assertRaisesRegex(ValueError, 'Conflicting'):
            machines.collection()

    def test_unknown_fields_kinds_and_abi_combinations_are_rejected(self):
        path = machines.ROOT / 'machines/fm2op/machine.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        for change in (dict(extra=1), dict(kind='instrument'), dict(display='segments'), dict(compiler='opxy'),
                       dict(sources=['../macroosc/engine.cpp'])):
            value = dict(copy.deepcopy(original), **change)
            text = json.dumps(value)
            real = Path.read_text
            with self.subTest(change=change), mock.patch.object(
                    Path, 'read_text', lambda self, *a, **k: text if self.name == 'machine.json' else real(self, *a, **k)):
                with self.assertRaises(ValueError):
                    machines.machine('fm2op')


if __name__ == '__main__':
    unittest.main()
