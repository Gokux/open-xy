"""Generate a target's startup continuations from its ordered engine prefixes."""
from pathlib import Path
import re

from .definitions import ROOT
from .formats import require

TEMPLATE = 'sdk/platform/opxy-1.2.0/startup.s.in'
MAX_ENGINES = 32


def _load(register, prefix, kind):
    return [f'    {register}.H = {prefix}_{kind}_id;', f'    {register}.L = {prefix}_{kind}_id;']


def _register(prefix):
    return [*_load('R0', prefix, 'engine'), *_load('R1', prefix, 'page'),
            f'    CALL {prefix}_register_checked_draft;']


def _tail_call(target):
    return ['    R0 = R4;', '    R1 = R5;', '    R2 = R6;', '    SP += 12;',
            '    (R7:4, P5:3) = [SP++];', '    UNLINK;', f'    JUMP.L {target};']


def render(prefixes, effects=(), stock_page=()):
    """stock_page: engines that show a stock page (e.g. sample engines on the
    sampler page); they register on the GUI role without an own-page guard."""
    require(1 <= len(prefixes) <= MAX_ENGINES and len(set(prefixes)) == len(prefixes),
            'Startup needs distinct engine prefixes')
    require(len(set(effects)) == len(effects) <= MAX_ENGINES and not set(effects) & set(prefixes),
            'Startup needs distinct effect prefixes')
    require(set(stock_page) <= set(prefixes), 'Stock-page engines must be listed engines')
    for prefix in (*prefixes, *effects):
        require(re.fullmatch(r'[a-z][a-z0-9_]{0,31}', prefix) is not None, 'Invalid engine prefix')
    synth = [line for prefix in prefixes for line in _register(prefix)]
    fx = [line for prefix in effects for line in (*_load('R0', prefix, 'fx'), *_load('R1', prefix, 'fx_page'),
                                                 f'    CALL {prefix}_fx_register_checked;')]
    screen = []
    for index, prefix in enumerate(prefixes):
        after = '.Lscreen_done' if index + 1 == len(prefixes) else f'.Lscreen_{prefixes[index + 1]}'
        if index:
            screen.append(f'.Lscreen_{prefix}:')
        if prefix in stock_page:
            screen += _register(prefix)
            continue
        screen += [*_load('R0', prefix, 'page'), f'    CALL {prefix}_screen_register_checked;',
                   '    CC = R0 == 1;', f'    IF !CC JUMP {after};', *_register(prefix)]
    routes = []
    for prefix in reversed(prefixes[1:]):
        routes += ['    R0 = R5;', f'    CALL {prefix}_name_matches;', '    CC = R0 == 1;',
                   f'    IF CC JUMP .Lcatalog_{prefix};']
    routes += _tail_call(f'{prefixes[0]}_catalog_checked')
    for prefix in reversed(prefixes[1:]):
        routes += [f'.Lcatalog_{prefix}:', *_tail_call(f'{prefix}_catalog_checked')]
    source = (ROOT / TEMPLATE).read_text(encoding='utf-8')
    for key, lines in (('FX_REGISTRATIONS', fx), ('SYNTH_REGISTRATIONS', synth), ('SCREEN_REGISTRATIONS', screen),
                       ('CATALOG_ROUTES', routes)):
        require(source.count('@' + key + '@') == 1, 'Startup template placeholder missing')
        source = source.replace('@' + key + '@', '\n'.join(lines))
    require('@' not in source, 'Unexpanded startup template')
    return source


def generate(directory, prefixes, effects=(), stock_page=()):
    destination = Path(directory) / 'startup.generated.s'
    destination.write_text(render(prefixes, effects, stock_page), encoding='utf-8', newline='\n')
    return destination
