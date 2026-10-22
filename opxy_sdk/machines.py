"""Machine discovery: each machines/<id>/machine.json declares what the SDK builds.

A machine's folder name is its stock name: the engine type the device lists,
its catalog and preset entries, its screen file and its symbol prefix.
machine.json declares only the engine/FX and page IDs. Saved presets and Open-XY layouts refer to
both, so they never change once published; the SDK checks them against the
stock tables and the collection.
"""
from dataclasses import dataclass
import json
import re

from .definitions import ROOT, stock_name, validate_definition
from .formats import require
from .stock_tables import ENGINE_COUNT, ENGINE_SENTINEL, PAGE_SENTINEL, check_assignment

KINDS = ('synth', 'sample', 'effect')
COLLECTION = ROOT / 'profiles/collection.json'
# Stock 1.2.0 registrations (docs/abi-1.2.0.md).
STOCK_ENGINE_IDS = frozenset({2, 3, 4, 6, 7, 18, 19, 20, 22, 29, 30, 31, 32})
SAMPLE_PAGES = frozenset({2, 7})  # stock sampler/multisampler and drum pages
FREE_FX_IDS = frozenset({1, 2, 3, 4, 6, 7, 8, 11})
FX_PAGE = 21


@dataclass(frozen=True)
class Machine:
    id: str
    kind: str
    name: str
    description: str
    display: str
    sources: tuple
    includes: tuple
    definition: dict
    identity: dict
    preset_defaults: dict

    # The stock name and the symbol prefix are the machine's name.
    @property
    def native_name(self):
        return self.id

    @property
    def prefix(self):
        return self.id

    @property
    def root(self):
        return ROOT / 'machines' / self.id


def _relative(machine_root, value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_./-]+', value) and
            '..' not in value.split('/') and not value.startswith('/'), 'Invalid machine path: ' + str(value))
    path = (machine_root / value).resolve()
    require(path.is_relative_to(machine_root.resolve()) and path.exists(), 'Missing machine path: ' + value)
    return value


def _identity(kind, display, value):
    require(isinstance(value, dict), 'machine.json needs an identity')
    slot = 'effect' if kind == 'effect' else 'engine'
    require(set(value) == {slot, 'page'}, 'Unexpected identity fields')
    number, page = value[slot], value['page']
    require(type(number) is int and type(page) is int, 'IDs must be integers')
    if kind == 'effect':
        require(number in FREE_FX_IDS and page == FX_PAGE,
                'Effects use an FX ID stock leaves unregistered, on the stock FX page')
    else:
        check_assignment(number, page)
        require(number not in STOCK_ENGINE_IDS, 'Engine ID is registered by stock')
        require(display == 'stock' or page > PAGE_SENTINEL,
                'A machine with its own screen needs a relocated page above %d' % PAGE_SENTINEL)
    if kind == 'sample':
        require(ENGINE_SENTINEL < number < ENGINE_COUNT and page in SAMPLE_PAGES,
                'Sample engines need a relocated-table engine ID (34..62) and a stock sample page')
    return {slot: number, 'page': page}


def machine(identity):
    stock_name(identity)
    root = ROOT / 'machines' / identity
    path = root / 'machine.json'
    require(path.is_file() and path.resolve() == path.absolute(), 'Unknown or redirected machine: ' + identity)
    value = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(value, dict) and value.get('schema') == 1 and
            set(value) <= {'schema', 'kind', 'description', 'identity', 'sources', 'includes', 'presetDefaults'},
            'Unexpected machine.json fields: ' + identity)
    kind = value.get('kind')
    require(kind in KINDS, 'Unknown machine kind: ' + str(kind))
    require(isinstance(value.get('description'), str) and 0 < len(value['description']) <= 160,
            'Machine needs a short description')
    sources = tuple(_relative(root, s) for s in value.get('sources', ()))
    includes = tuple(_relative(root, s) for s in value.get('includes', ()))
    require(all(s.endswith(('.cc', '.cpp')) for s in sources), 'Extra sources must be C++ translation units')
    definition = validate_definition(json.loads((root / 'definition.json').read_text(encoding='utf-8')), kind)
    require(definition['id'] == identity, 'Machine directory and definition identity disagree')
    # A synth draws its own screen; sample engines and effects use a stock page.
    display = definition['resources']['display']['kind'] if kind == 'synth' else 'stock'
    if kind != 'synth':
        require(not sources and not includes, 'Sample engines and effects compile one fx.cpp or sample.cpp')
    if kind == 'sample' and definition['resources'].get('drumControls', 0):
        require(value['identity']['page'] == 7, 'Drum control callbacks need stock page 7')
    defaults = value.get('presetDefaults', {})
    require(isinstance(defaults, dict) and set(defaults) <= {'amp'}, 'Invalid preset defaults')
    amp = defaults.get('amp', {})
    require(isinstance(amp, dict) and set(amp) <= {'attack', 'decay', 'release', 'sustain'} and
            all(type(v) is int and 0 <= v <= 32767 for v in amp.values()), 'Invalid preset amp defaults')
    return Machine(id=identity, kind=kind, name=definition['name'], description=value['description'],
                   display=display, sources=sources, includes=includes,
                   definition=definition,
                   identity=_identity(kind, display, value['identity']), preset_defaults=defaults)


def discovered():
    """Every machine folder in the repository, in name order."""
    return [machine(path.parent.name) for path in sorted((ROOT / 'machines').glob('*/machine.json'))]


def collection():
    """Machines in firmware order: the order sets startup, catalog and link layout."""
    value = json.loads(COLLECTION.read_text(encoding='utf-8'))
    identities = value['machines']
    require(isinstance(identities, list) and identities and len(set(identities)) == len(identities),
            'Collection needs distinct machines')
    machines = [machine(identity) for identity in identities]
    engines = [m.identity['engine'] for m in machines if 'engine' in m.identity]
    effects = [m.identity['effect'] for m in machines if 'effect' in m.identity]
    pages = [m.identity['page'] for m in machines if m.display != 'stock']
    require(len(set(engines)) == len(engines) and len(set(effects)) == len(effects) and len(set(pages)) == len(pages),
            'Conflicting engine, effect or page ID')
    return machines


def by_kind(machines, *kinds):
    return [m for m in machines if m.kind in kinds]
