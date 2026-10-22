"""Compare browser output to independent GNU ELF and Python container readers."""
import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from opxy_sdk.formats import elf32, ldr, mapped_offset, require, sha
from opxy_sdk import screen, startup_label, sample_hooks
from opxy_sdk.firmware import HOOKS, assemble, branch_instruction, decode_branch


def check_startup_label(module, symbols, base):
    """The linked thunk is exactly the reviewed one: R2 replay, stock draw call, stock continuation."""
    entry, text = symbols[startup_label.SYMBOL], symbols['kit_startup_label_text']
    require(startup_label.thunk_ok(module, entry['value'] - base, entry['size'], text['value']),
            'Startup thunk changed')
    at = text['value'] - base
    require(text['size'] == len(startup_label.LABEL) and module[at:at + text['size']] == startup_label.LABEL,
            'Unexpected startup label')


# sdk/platform/opxy-1.2.0/fallback.s: kit_absent returns 0; kit_catalog_stock
# returns 0 for the missing-engine ID 33 and otherwise tail-jumps to stock.
FALLBACK_BEFORE_JUMP = bytes.fromhex('0060 1000 0b61 1a08 0318')
FALLBACK_AFTER_JUMP = bytes.fromhex('0060 1000')


def check_fallbacks(module, symbols, base):
    """Linked absent-machine stubs are the reviewed bytes; their one jump reaches stock catalog insertion."""
    start = symbols['kit_absent']['value']
    require(symbols['kit_absent']['size'] == 4 and symbols['kit_catalog_stock'] ==
            dict(symbols['kit_catalog_stock'], value=start + 4, size=14), 'Unexpected absent-machine stub layout')
    at, jump = start - base, start + len(FALLBACK_BEFORE_JUMP)
    code = module[at:at + len(FALLBACK_BEFORE_JUMP) + 4 + len(FALLBACK_AFTER_JUMP)]
    require(code.startswith(FALLBACK_BEFORE_JUMP) and code.endswith(FALLBACK_AFTER_JUMP),
            'Absent-machine stubs differ from their source')
    require(decode_branch(jump, code[len(FALLBACK_BEFORE_JUMP):len(FALLBACK_BEFORE_JUMP) + 4]) == (0x8d5bbaa0, False),
            'Absent-machine stub does not delegate to stock catalog insertion')


def main():
    directory, stock_file, content = map(lambda p: Path(p).resolve(), sys.argv[1:])
    subprocess.run(['node', str(ROOT / 'tools/check_browser_firmware.mjs'), str(directory), str(stock_file), str(content)], check=True)
    kit = json.loads((directory / 'kit.json').read_text(encoding='utf-8'))
    stock = stock_file.read_bytes()
    require(sha(stock) == kit['profile']['stock_sha256'], 'Unexpected stock input')
    # 0x8c0c88bc measures the text using this stock width table, adding
    # one pixel per glyph. The existing draw call centers it at x=240.
    offset = mapped_offset(ldr(stock), 0x840131c4, 96)
    widths = stock[offset:offset + 96]
    label = startup_label.LABEL[:-1]
    require(all(32 <= c < 128 for c in label), 'Startup label outside stock font')
    width = sum(widths[c - 32] + 1 for c in label)
    left = 240 - width // 2
    require(width == 97 and 100 <= left and left + width <= 400, 'Startup label exceeds its drawing area')
    # The browser links the native objects in native order, so selecting every
    # machine reproduces the native package exactly.
    everything = directory / 'reference' / str(2 ** len(kit['machines']) - 1)
    require(everything.with_suffix('.ldr').read_bytes() == (directory / 'source/candidate/os.ldr').read_bytes(),
            'Browser firmware for the full collection differs from the native package')
    for index, result in enumerate(json.loads((directory / 'reference/selections.json').read_text()), 1):
        prefix = directory / 'reference' / str(index)
        sections, symbols = elf32(prefix.with_suffix('.elf').read_bytes())
        module = prefix.with_suffix('.bin').read_bytes()
        require(sha(module) == result['module_sha256'], 'GNU module digest differs')
        low = kit['profile']['module_base']
        check_fallbacks(module, symbols, low)
        check_startup_label(module, symbols, low)
        require(symbols['__extensions_initialized_end']['value'] - low == result['sizes']['initialized'] and
                symbols['__extensions_module_end']['value'] - low == result['sizes']['allocated'] and
                sections.get('.bss', {}).get('size', 0) == result['sizes']['bss'], 'GNU memory allocation differs')
        for name, value in result['globals'].items():
            require(symbols[name]['value'] == value, 'GNU symbol differs: ' + name)
        profile = copy.deepcopy(kit['profile'])
        for patch in profile['patches']:
            address = int(patch['address'], 16)
            if address in HOOKS:
                symbol, call = HOOKS[address]
                target = symbols[symbol]['value']
                width = patch['length']
                if width == 8:
                    require(call, 'Eight-byte hook must be an absolute call')
                    code = sample_hooks.absolute_call(target)
                else:
                    require(width in (4, 6), 'Unsupported relative-hook footprint')
                    code = branch_instruction(address, target, call) + bytes(width - 4)
                patch['after'] = code.hex()
            elif startup_label.allowed(profile, patch):
                patch['after'] = startup_label.jump(symbols[startup_label.SYMBOL]['value']).hex()
        expected = assemble(stock, module, profile, kit['profile'], len(profile['patches']))
        require(expected == prefix.with_suffix('.ldr').read_bytes(), 'Python/browser firmware differs')
        selected = [m for m in kit['machines'] if m['id'] in result['selected']]
        catalog = json.loads((content / 'op1_factory.json').read_bytes())
        for machine in selected:
            key = 'fx_types' if machine['kind'] == 'effect' else 'engine_types'
            catalog[key].append(json.loads(machine['catalog'].strip().lstrip(',')))
        actual_catalog = (prefix / 'content/op1_factory.json').read_bytes()
        require(json.loads(actual_catalog) == catalog, 'Browser catalog differs')
        expected_files = {'os.ldr': expected, 'content/op1_factory.json': actual_catalog}
        for machine in selected:
            if machine['kind'] != 'effect':
                name = 'content/presets/' + machine['id'] + '/default.json'
                data = (prefix / name).read_bytes()
                preset = json.loads(data)
                definition = json.loads((ROOT / 'machines' / machine['id'] / 'definition.json').read_bytes())
                defaults = [math.floor(p['default'] * 32767 + .5) for p in definition['parameters']]
                defaults += [0] * (8 - len(defaults))
                entry = json.loads(machine['catalog'].strip().lstrip(','))
                require(preset['type'] == entry['type'] and preset['platform'] == 'OP-XY' and
                        preset['version'] == 4 and preset['engine']['params'] == defaults and
                        preset['regions'] == [] and preset['fx']['active'] is False and
                        preset['lfo']['active'] is False, 'Default preset differs from instrument definition')
                expected_files[name] = data
            if machine.get('artwork'):
                name = 'content/display/' + machine['asset']
                art = screen.compose(machine['artwork'].encode())
                require((prefix / name).read_bytes() == art, 'Browser artwork differs')
                expected_files[name] = art
        with zipfile.ZipFile(prefix.with_suffix('.zip')) as archive:
            require(set(archive.namelist()) == set(expected_files) and archive.testzip() is None, 'Invalid ZIP file')
            for name, data in expected_files.items():
                require(archive.read(name) == data, 'ZIP payload differs')
    print('Independent GNU/Python verification passed for every selection (module, symbols, BSS, LDR, assets, ZIP).')


if __name__ == '__main__':
    main()
