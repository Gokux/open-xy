"""Exact stock 1.2.0 GUI boundaries for the shared custom sample-page service.

These are platform contracts, independent of machine names, IDs or controls.
All addresses, displaced bytes and loader offsets are authenticated by the
firmware profile and whole-stock hash before packaging.
"""
import struct
from .formats import require

# site: symbol, original bytes, loader offset
EDITS = {
    0x8c0b1e76: ('sdk_sample_ui_engine', '00de588db45e0000', 0xe9236),
    0x8c0b21c6: ('sdk_sample_region_control', '00de4d8db8ca0000', 0xe9586),
    0x8c0b3290: ('sdk_sample_press_engine', '00de588db45e0000', 0xea650),
    0x8d5ab6da: ('sdk_sample_live_pitch_kind', '00e34752', 0x1e2ab2),
    0x8d58d9ca: ('sdk_sample_octave_store', 'ffe37db1', 0x1c4da6),
    0x8c0a2cee: ('sdk_sample_assignment_frames', '00de4f8d46d10000', 0xda0ae),
    0x8c0a2de4: ('sdk_sample_assign_region', '00de588d24820000', 0xda1a4),
    0x8d5882d8: ('sdk_sample_assign_fade', '00de0204d80f0000', 0x1bf6b4),
    0x8d5878a8: ('extensions_sample_key', '00e80000', 0x1bec84),
    0x8d5347de: ('sdk_sample_drum_display', 'ffe32df6', 0x16bbba),
    0x8d53465a: ('sdk_sample_drum_range', 'fde34919', 0x16ba36),
    0x8d5349e4: ('sdk_sample_drum_fade', '48a1404d', 0x16bdc0),
    0x8c0a21c0: ('sdk_sample_pending_retry', '05da0108c0f70000', 0xd9580),
    0x8c0a219c: ('sdk_sample_active_retry', '0cda0108dcf70000', 0xd955c),
}


def allowed(profile, patch):
    item = EDITS.get(int(patch['address'], 16))
    return (profile['id'] == 'opxy-1.2.0' and item is not None and patch['before'] == item[1] and
            patch['length'] == len(bytes.fromhex(item[1])) and int(patch['file_offset'], 16) == item[2])


def absolute_call(target):
    require(0 <= target <= 0xffffffff and target % 2 == 0, 'Invalid absolute call target')
    return struct.pack('<4H', 0xde00, target >> 16, target & 65535, 0)


def absolute_target(data):
    require(len(data) == 8, 'Absolute call must occupy eight bytes')
    opcode, high, low, zero = struct.unpack('<4H', data)
    require(opcode == 0xde00 and zero == 0 and low % 2 == 0, 'Invalid absolute call encoding')
    return high << 16 | low
