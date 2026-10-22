"""Version-bound OS container assembly shared by curated engine builds."""
import struct
from .formats import header, ldr, mapped_offset, require, sha
from .pipeline import check_patch_boundaries
from . import startup_label
from . import sample_hooks

HOOKS = {
    0x8d5063b2: ('extensions_synth_exit', False),
    0x8d5231e4: ('extensions_screen_exit', False),
    0x8d523240: ('extensions_screen_exit', False),
    0x8d4e09d6: ('extensions_catalog_checked', True),
    0x8d4e0b78: ('extensions_catalog_checked', True),
    0x8d5b5b38: ('extensions_sample_classify', False),
    0x8d5ab9a0: ('extensions_sample_note_region', True),
    0x8d50b5d8: ('sdk_sample_cache_destroy', True),
    0x8d51de40: ('sdk_sample_progress_frame', True),
    0x8d4dad2e: ('sdk_sample_cache_snapshot', True),
    0x8d4d957e: ('sdk_sample_cache_ipc_priority', True),
    0x8d4d9e26: ('sdk_sample_cache_gui_add', True),
    0x8d4d8ede: ('sdk_sample_cache_audio_add', True),
    0x8d4d9dde: ('sdk_sample_cache_reset', True),
    0x8d4d8e88: ('sdk_sample_cache_reset', True),
    0x8d50bf1c: ('sdk_sample_cache_worker', True),
    0x8d4d9dd2: ('sdk_sample_cache_send', True),
}
HOOKS.update({site: (item[0], site != 0x8d5878a8) for site, item in sample_hooks.EDITS.items()})


def branch_instruction(site, destination, call):
    delta = destination - site
    require(delta % 2 == 0 and -(1 << 24) <= delta < (1 << 24), 'Branch outside signed PC-relative range')
    encoded = (delta // 2) & 0xffffff
    return struct.pack('<HH', (0xe300 if call else 0xe200) | (encoded >> 16), encoded & 0xffff)


def decode_branch(site, instruction):
    require(len(instruction) == 4, 'Branch must occupy four bytes')
    first, second = struct.unpack('<HH', instruction)
    require(first & 0xfe00 == 0xe200, 'Unexpected branch opcode')
    offset = ((first & 0xff) << 16) | second
    if offset & 0x800000:
        offset -= 1 << 24
    return site + offset * 2, bool(first & 0x100)


def assemble(stock, module, profile, original_profile, edits=7):
    require(sha(stock) == original_profile['stock_sha256'] and len(stock) == original_profile['stock_bytes'],
            'Expected exact decrypted stock OP-XY 1.2.0')
    require(len(module) > 0 and len(module) <= original_profile['reserved_bytes'], 'Invalid module size')
    require(len(profile['patches']) == len(original_profile['patches']) == edits, f'Expected {edits} edit intervals')
    for patch, original in zip(profile['patches'], original_profile['patches']):
        require(all(patch[k] == original[k] for k in ('address', 'before', 'file_offset', 'length')),
                'Changed patch boundary')
        site = int(patch['address'], 16)
        if startup_label.allowed(original_profile, original):
            target = startup_label.destination(bytes.fromhex(patch['after']))
            require(original_profile['module_base'] <= target < original_profile['module_base'] + len(module),
                    'Startup hook does not target module')
        elif site not in HOOKS:
            require(patch['after'] == original['after'], 'Changed heap reservation')
        else:
            instruction = bytes.fromhex(patch['after'])
            if original['length'] == 8:
                target, call = sample_hooks.absolute_target(instruction), True
            else:
                require(instruction[4:] == b'\0' * (original['length'] - 4), 'Changed hook padding')
                target, call = decode_branch(site, instruction[:4])
            require(call == HOOKS[site][1] and original_profile['module_base'] <= target < original_profile['module_base'] + len(module),
                    'Hook does not target module')
    check_patch_boundaries(profile, edits)
    blocks = ldr(stock)
    require(len(blocks) == original_profile['stock_records'], 'Unexpected stock records')
    first, final = blocks[0], blocks[-1]
    require(first['code'] & 0xffff == 0x5004 and first['count'] == 0 and
            final['code'] & 0xffff == 0x8004 and final['count'] == 0, 'Unsupported FIRST/FINAL')
    low, high = original_profile['module_base'], original_profile['module_base'] + original_profile['reserved_bytes']
    overlapping = [b for b in blocks if b['target'] < high and low < b['target'] + b['count']]
    require(len(overlapping) == 1, 'Unexpected writes to shared reservation')
    fill = overlapping[0]
    require(fill['fill'] and fill['argument'] == 0 and fill['target'] == original_profile['heap_fill_base'] and
            fill['count'] == original_profile['heap_fill_bytes'] and fill['target'] <= low and high <= fill['target'] + fill['count'],
            'Shared state not zero-filled by unchanged stock loader record')
    patched = bytearray(stock)
    for patch in profile['patches']:
        address = int(patch['address'], 16)
        before, after = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
        offset = mapped_offset(blocks, address, len(before))
        require(offset == int(patch['file_offset'], 16) and stock[offset:offset + len(before)] == before,
                'Patch preimage mismatch')
        patched[offset:offset + len(after)] = after
    at = final['offset']
    candidate = bytes(patched[:at]) + header(4, low, len(module), 0) + module + bytes(patched[at:])
    candidate = header(0x5004, first['target'], 0, len(candidate) - 16) + candidate[16:]
    result = ldr(candidate)
    require(len(result) == len(blocks) + 1 and result[0]['target'] == first['target'], 'Entry/record count changed')
    require(candidate[-16:] == stock[-16:], 'FINAL entry changed')
    # Recover the original image from candidate using only the known edits,
    # the new module record and FIRST length/checksum, then compare every byte.
    restored = bytearray(candidate[:at] + candidate[at + 16 + len(module):])
    restored[:16] = stock[:16]
    for patch in profile['patches']:
        offset = int(patch['file_offset'], 16)
        restored[offset:offset + patch['length']] = bytes.fromhex(patch['before'])
    require(bytes(restored) == stock, 'Unauthorized difference outside exact OS edits')
    return candidate
