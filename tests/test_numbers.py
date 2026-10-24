"""Machine numbers (engine, effect and page IDs) reach compiled code only through link-time
symbols, so one set of objects serves any numbering a layout assigns."""
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from tooling.adapters import (generate_display, generate_fx_object, generate_registration, generate_sample_callbacks,
                              generate_sample_voice, generate_screen, generate_synth_controls, generate_voice)
from tooling.machines import by_kind, collection
from tooling.startup import generate as generate_startup


def renumbered(m):
    """The same machine under other numbers. A sample engine's page is its stock page
    (sampler or drum), part of what it is, so only its engine changes."""
    identity = dict(m.identity)
    if m.kind == 'effect':
        identity['effect'] = 11 if identity['effect'] != 11 else 8
    else:
        identity['engine'] = 62 if identity['engine'] != 62 else 61
        if m.kind == 'synth':
            identity['page'] = 127 if identity['page'] != 127 else 126
    return replace(m, identity=identity)


def sources(directory, machines):
    """Every generated source of a collection, by name."""
    directory = Path(directory)
    for m in machines:
        folder = directory / m.id
        folder.mkdir()
        steps = {'synth': (generate_voice, generate_display, generate_screen, generate_registration),
                 'effect': (generate_registration, generate_fx_object),
                 'sample': (generate_registration, generate_sample_voice)}[m.kind]
        for step in steps:
            if step is generate_display:
                step(folder, machine=m)
            else:
                step(folder, m)
    shared = directory / 'sdk'
    shared.mkdir()
    generate_sample_callbacks(shared, machines)
    generate_synth_controls(shared, machines)
    generate_startup(shared, [m.prefix for m in by_kind(machines, 'synth', 'sample')],
                     [m.prefix for m in by_kind(machines, 'effect')], [m.prefix for m in by_kind(machines, 'sample')])
    return {p.relative_to(directory).as_posix(): p.read_bytes() for p in sorted(directory.rglob('*')) if p.is_file()}


class LinkTimeNumbers(unittest.TestCase):
    def test_generated_sources_do_not_depend_on_machine_numbers(self):
        machines = collection()
        self.assertEqual({m.kind for m in machines}, {'synth', 'effect', 'sample'})
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            before, after = sources(first, machines), sources(second, [renumbered(m) for m in machines])
        self.assertEqual(sorted(before), sorted(after))
        for name in before:
            with self.subTest(source=name):
                self.assertEqual(before[name], after[name])


if __name__ == '__main__':
    unittest.main()
