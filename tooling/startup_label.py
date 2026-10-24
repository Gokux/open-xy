"""The boot-screen version label: one display-only edit in stock OS startup."""
from pathlib import Path
import re
import struct

from .formats import require
from .pipeline import ROOT

PROFILE = 'opxy-1.2.0'
SITE = 0x8c0b9114
CONTINUATION = 0x8c0b911e
DRAW = 0x8c0b7ba8
BEFORE = bytes.fromhex('32e414000207ffe347f5')
OBJECT = 'sdk/startup_label.o'
SYMBOL = 'kit_startup_label'
# The release version, which the builder shows too; the label adds the stock OS it extends.
VERSION = (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
require(re.fullmatch(r'\d+\.\d+\.\d+', VERSION) is not None, 'VERSION is <major>.<minor>.<patch>')
LABEL = f'OPEN {VERSION}-1.2.0'.encode('ascii') + b'\0'
TEMPLATE = 'sdk/platform/opxy-1.2.0/startup_label.s.in'


def generate(directory):
    """The label unit's assembly, with this release's label."""
    source = (ROOT / TEMPLATE).read_text(encoding='utf-8')
    require(source.count('@LABEL@') == 1, 'Startup label template placeholder missing')
    destination = Path(directory) / 'startup_label.s'
    destination.write_text(source.replace('@LABEL@', LABEL[:-1].decode('ascii')), encoding='utf-8', newline='\n')
    return destination


def jump(destination):
    require(0 <= destination <= 0xffffffff and destination % 2 == 0, 'Invalid absolute jump')
    return struct.pack('<4H', 0xdc00, destination >> 16, destination & 0xffff, 0) + b'\0\0'


def destination(instruction):
    require(len(instruction) == 10, 'Startup hook must occupy ten bytes')
    opcode, high, low, zero, nop = struct.unpack('<5H', instruction)
    require(opcode == 0xdc00 and zero == nop == 0 and low % 2 == 0, 'Unexpected startup hook encoding')
    return high << 16 | low


def allowed(profile, patch):
    return (profile['id'] == PROFILE and int(patch['address'], 16) == SITE and
            bytes.fromhex(patch['before']) == BEFORE and patch['length'] == len(BEFORE) and
            int(patch['file_offset'], 16) == 0xf04d4 and patch.get('symbol') == SYMBOL)


def thunk_ok(module, offset, size, text):
    """The linked thunk replays the stock R2 load, loads R0 = text, calls the stock draw and resumes."""
    code = module[offset:offset + size]
    return (size == 28 and code[:4] == bytes.fromhex('32e41400') and
            code[4:12] == struct.pack('<4H', 0xe140, text >> 16, 0xe100, text & 0xffff) and
            code[12:20] == struct.pack('<4H', 0xde00, DRAW >> 16, DRAW & 0xffff, 0) and
            code[20:28] == struct.pack('<4H', 0xdc00, CONTINUATION >> 16, CONTINUATION & 0xffff, 0))
