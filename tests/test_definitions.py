import copy
import re
from types import SimpleNamespace
import tempfile
import json
import unittest

from opxy_sdk.adapters import catalog_defaults, catalog_entry, generate_screen, generate_segments, screen_bytes
from opxy_sdk.definitions import ROOT, validate_definition
from opxy_sdk.machines import machine
from opxy_sdk.native import drawing_ids, segment_ids


class Definitions(unittest.TestCase):
    def setUp(self):
        self.engine = json.loads((ROOT / 'machines/fm2op/definition.json').read_text(encoding='utf-8'))

    def test_catalog_entries_keep_the_reviewed_stock_layout(self):
        # Byte layout of the entries inserted into the stock catalog.
        self.assertEqual(catalog_entry(machine('fm2op')).encode(),
                         b',\n        {\n            "type": "fm2op",\n            "default_params": '
                         b'[10922, 15728, 3932, 18022, 0, 0, 0, 0]\n        }\n')
        self.assertEqual(catalog_entry(machine('macroosc')).encode(),
                         b',\n        {\n            "type": "macroosc",\n            "default_params": '
                         b'[0, 16384, 16384, 16384, 0, 0, 0, 0]\n        }\n')

    def test_bad_controls_fail_before_generating_code(self):
        for value in (-0.1, 1.1, True, float('nan'), float('inf'), 10 ** 400):
            invalid = copy.deepcopy(self.engine)
            invalid['parameters'][0]['default'] = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(ValueError):
                validate_definition(invalid, 'synth')
        invalid = copy.deepcopy(self.engine)
        invalid['parameters'][1]['id'] = invalid['parameters'][0]['id']
        with self.assertRaisesRegex(ValueError, 'Duplicate'): validate_definition(invalid, 'synth')
        invalid = copy.deepcopy(self.engine)
        invalid['parameters'][0]['mapping']['values'] = [1, 0.5, 2]
        with self.assertRaisesRegex(ValueError, 'increase'): validate_definition(invalid, 'synth')
        invalid = copy.deepcopy(self.engine)
        invalid['parameters'][0]['label'] = '<script>'
        with self.assertRaises(ValueError): validate_definition(invalid, 'synth')

    def test_mappings_must_be_supported(self):
        invalid = copy.deepcopy(self.engine)
        invalid['parameters'][0]['mapping']['kind'] = 'javascript'
        with self.assertRaisesRegex(ValueError, 'Unsupported'): validate_definition(invalid, 'synth')
        invalid = copy.deepcopy(self.engine)
        invalid['presets']['Glass']['unknown'] = 0.5
        with self.assertRaises(ValueError): validate_definition(invalid, 'synth')
        # Each linear control has one spelling.
        for mapping in (dict(kind='anchors', values=[0, 1]), dict(kind='power', maximum=1, exponent=1),
                        dict(kind='linear', minimum=1, maximum=1)):
            invalid = copy.deepcopy(self.engine)
            invalid['parameters'][0]['mapping'] = mapping
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                validate_definition(invalid, 'synth')
        valid = copy.deepcopy(self.engine)
        valid['parameters'][0]['mapping'] = dict(kind='linear', minimum=-12, maximum=12)
        valid['parameters'][0]['display'] = 'semitones'
        validate_definition(valid, 'synth')

    def test_catalog_uses_q15_with_positive_half_rounding(self):
        changed = copy.deepcopy(self.engine)
        changed['parameters'][0]['default'] = 0.5
        self.assertEqual(catalog_defaults(changed)[0], 16384)

    def test_resource_declarations_reject_unknown_layouts_and_rates(self):
        for key, value in (('voiceBytes', 0), ('voiceBytes', 41),
                           ('voiceAlignment', 3), ('voiceAlignment', 16),
                           ('outputPeakQ31', 0), ('voiceBytes', True)):
            changed = copy.deepcopy(self.engine)
            changed['resources'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_definition(changed, 'synth')
        for key in ('blockFrames', 'sampleRate'):
            changed = copy.deepcopy(self.engine)
            changed['resources'][key] = 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'resources'):
                validate_definition(changed, 'synth')
        changed = copy.deepcopy(self.engine)
        changed['cppNamespace'] = 'fm2op'
        with self.assertRaisesRegex(ValueError, 'definition'): validate_definition(changed, 'synth')
        for name in ('delete', 'opxy'):
            changed = copy.deepcopy(self.engine)
            changed['id'] = name
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'keyword'):
                validate_definition(changed, 'synth')

    def test_displays_declare_their_shape_within_limits(self):
        for key, value in (('stateBytes', 61), ('stateBytes', 0),
                           ('stateAlignment', 3), ('stateAlignment', 8),
                           ('paths', 0), ('paths', 5), ('points', 1), ('points', 65),
                           ('nodes', 1), ('nodes', 65), ('palette', 0), ('palette', 17), ('kind', 'vector')):
            changed = copy.deepcopy(self.engine)
            changed['resources']['display'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_definition(changed, 'synth')
        segments = machine('macroosc').definition
        for key, value in (('characters', 0), ('characters', 9), ('textControls', [4]),
                           ('textControls', [1, 0]), ('textControls', [0, 0]), ('glow', 4), ('glow', -1),
                           ('dials', 5), ('dials', True)):
            changed = copy.deepcopy(segments)
            changed['resources']['display'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_definition(changed, 'synth')

    def test_every_kind_shares_the_controls_schema(self):
        for identity in ('timestretch', 'decimate'):
            m = machine(identity)
            value = copy.deepcopy(m.definition)
            value['parameters'][0]['label'] = 'Feedback amount'
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, 'Control labels'):
                validate_definition(value, m.kind)
        effect = copy.deepcopy(machine('decimate').definition)
        effect['resources']['voiceCapacity'] = 8
        with self.assertRaisesRegex(ValueError, 'resources'): validate_definition(effect, 'effect')
        sample = copy.deepcopy(machine('timestretch').definition)
        sample['parameters'] = []
        with self.assertRaisesRegex(ValueError, 'Control count'): validate_definition(sample, 'sample')


    def test_renderers_generate_for_every_declared_shape(self):
        shapes = [dict(kind='drawing', stateBytes=4, stateAlignment=4, paths=1, points=2, nodes=64, palette=1),
                  dict(kind='drawing', stateBytes=8, stateAlignment=8, paths=4, points=64, nodes=4, palette=16),
                  dict(kind='segments', characters=1, glow=0, dials=0, textControls=[]),
                  dict(kind='segments', characters=8, glow=3, dials=4, textControls=[0, 1, 2, 3])]
        for display in shapes:
            definition = copy.deepcopy(machine('fm2op').definition)
            definition['resources']['display'] = display
            validate_definition(definition, 'synth')
            m = SimpleNamespace(prefix='shape', native_name='shape', definition=definition)
            with self.subTest(display=display), tempfile.TemporaryDirectory() as directory:
                generate = generate_screen if display['kind'] == 'drawing' else generate_segments
                source = generate(directory, m).read_text(encoding='utf-8')
                self.assertNotIn('@', source)
                self.assertIn('.space %d' % screen_bytes(m), source)
                if display['kind'] == 'drawing':
                    ids = drawing_ids('shape', display)
                else:
                    names = segment_ids('shape', display)
                    ids = sum(names['glow_palette'], []) + names['segments'] + sum(names['glow'], []) + names['dials']
                self.assertEqual(re.findall(r'\.asciz "(shape_(?:node|palette|seg|glow|dial)_[0-9a-z_]+)"', source), ids)

if __name__ == '__main__':
    unittest.main()
