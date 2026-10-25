"""Project companions: what each saved machine number meant, by machine ID."""
import json
from pathlib import Path
import tempfile
import unittest

from tooling.machines import LAYOUT_FORMAT
from tooling.pipeline import config
from tooling.projects import (LIMIT, MACHINES, canonical, companion, companion_path, main, parse, saved_numbers, translation)

PROJECT = bytes(range(256)) * 4
SAVED = {'karplus': {'engine': 36, 'page': 84}, 'pingpong': {'effect': 40, 'page': 21},
         'timestretch': {'engine': 35, 'page': 7}}


def edited(document, **changes):
    return json.dumps(dict(document, **changes)).encode()


class Companions(unittest.TestCase):
    def test_round_trip_gives_the_saving_layout(self):
        document = parse(companion(PROJECT, SAVED))
        self.assertEqual(saved_numbers(document, PROJECT), SAVED)
        self.assertEqual(document['sections'][MACHINES]['profile'], config()['id'])

    def test_writers_emit_one_canonical_form(self):
        raw = companion(PROJECT, SAVED)
        self.assertEqual(raw, companion(PROJECT, dict(reversed(SAVED.items()))))
        self.assertEqual(raw, canonical(json.loads(raw)))
        self.assertTrue(raw.endswith(b'}\n') and b'\r' not in raw)
        self.assertGreater(raw.count(b'\n'), 20, 'one value per line')

    def test_project_saved_since_is_read_as_saved(self):
        # Stock, or firmware without companions, rewrote the project after the companion.
        document = parse(companion(PROJECT, SAVED))
        self.assertIsNone(saved_numbers(document, PROJECT + b'\0'))
        self.assertIsNone(saved_numbers(document, bytes(reversed(PROJECT))))

    def test_other_firmware_or_unknown_section_versions_are_ignored(self):
        document = parse(companion(PROJECT, SAVED, profile='opxy-9.9.9'))
        self.assertIsNone(saved_numbers(document, PROJECT))
        document = json.loads(companion(PROJECT, SAVED))
        document['sections'][MACHINES] = {'version': 2, 'anything': True}
        self.assertIsNone(saved_numbers(parse(json.dumps(document).encode()), PROJECT))

    def test_unknown_keys_and_sections_are_ignored_and_kept_while_they_apply(self):
        document = json.loads(companion(PROJECT, SAVED))
        document['written'] = 'later field'
        document['sections']['someone.tuning'] = {'version': 3, 'scale': [0, 2, 4]}
        previous = parse(json.dumps(document).encode())
        self.assertEqual(saved_numbers(previous, PROJECT), SAVED)
        kept = parse(companion(PROJECT, {'karplus': {'engine': 37, 'page': 85}}, previous))
        self.assertEqual(kept['sections']['someone.tuning'], {'version': 3, 'scale': [0, 2, 4]})
        dropped = parse(companion(PROJECT + b'!', SAVED, previous))
        self.assertEqual(set(dropped['sections']), {MACHINES})

    def test_invalid_companions_are_refused_whole(self):
        document = json.loads(companion(PROJECT, SAVED))
        for raw in (b'not json', b'[]', edited(document, format='other'), edited(document, version=2),
                    edited(document, version=0), edited(document, project={'bytes': 1, 'crc32': 'XYZ'}),
                    edited(document, sections={'nodot': {'version': 1}}),
                    edited(document, sections={'a.b': {'version': '1'}}),
                    edited(document, sections={MACHINES: {'version': 1, 'profile': 'x', 'machines': {'k': {'engine': 1}}}}),
                    b' ' * (LIMIT + 1)):
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                parse(raw)

    def test_translation_follows_machine_ids(self):
        here = {'karplus': {'engine': 41, 'page': 90}, 'pingpong': {'effect': 40, 'page': 21}}
        self.assertEqual(translation(SAVED, here), {
            ('engine', 36): 41, ('page', 84): 90,   # renumbered in this layout
            ('effect', 40): 40,                     # same number
            ('engine', 35): None, ('page', 7): None,  # not installed here
        })

    def test_command_writes_and_checks_beside_each_project(self):
        with tempfile.TemporaryDirectory() as directory:
            project, layout = Path(directory) / 'song.xy', Path(directory) / 'layout.json'
            project.write_bytes(PROJECT)
            layout.write_text(json.dumps({'format': LAYOUT_FORMAT, 'profile': config()['id'], 'machines': SAVED}))
            self.assertEqual(main(['write', '--layout', str(layout), str(project)]), 0)
            self.assertEqual(companion_path(project), Path(directory) / 'song.oxy')
            self.assertEqual(saved_numbers(parse(companion_path(project).read_bytes()), PROJECT), SAVED)
            self.assertEqual(main(['check', str(project)]), 0)


if __name__ == '__main__':
    unittest.main()
