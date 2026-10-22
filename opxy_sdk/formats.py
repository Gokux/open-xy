"""Bounded LDR and ELF32 readers; no assertions used for validation."""
import hashlib
import struct
from functools import reduce
from operator import xor


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def header(flags, target, count, argument):
    require(all(0 <= n <= 0xffffffff for n in (target, count, argument)), "Header field overflow")
    raw = bytearray(struct.pack('<IIII', 0xad000000 | flags, target, count, argument))
    raw[2] = reduce(xor, raw)
    return bytes(raw)


def ldr(data):
    require(0 < len(data) <= 16 * 1024 * 1024, "LDR size outside supported bounds")
    blocks, offset = [], 0
    while offset < len(data):
        require(len(blocks) < 10000 and offset + 16 <= len(data), "Invalid LDR block boundary")
        raw = data[offset:offset + 16]
        code, target, count, argument = struct.unpack('<IIII', raw)
        require(code >> 24 == 0xad and reduce(xor, raw) == 0, "Invalid LDR header/checksum")
        require(target + count <= 0x100000000, "LDR address overflow")
        fill = bool(code & 0x100)
        stored = 0 if fill else count
        require(offset + 16 + stored <= len(data), "LDR payload exceeds file")
        blocks.append(dict(offset=offset, code=code, target=target, count=count,
                           argument=argument, fill=fill, stored=stored))
        offset += 16 + stored
        if code & 0x8000:
            require(offset == len(data), "Trailing bytes after FINAL")
            return blocks
    raise ValueError("Missing FINAL record")


def mapped_offset(blocks, address, size):
    require(size > 0, "Empty address range")
    overlaps = [b for b in blocks if b['target'] < address + size and address < b['target'] + b['count']]
    require(len(overlaps) == 1, "Ambiguous load mapping")
    block = overlaps[0]
    require(not block['fill'] and block['target'] <= address and
            address + size <= block['target'] + block['count'], "Not a stored payload interval")
    return block['offset'] + 16 + address - block['target']


def elf32(data):
    require(len(data) >= 52 and data[:6] == b'\x7fELF\x01\x01', "Expected little-endian ELF32")
    require(struct.unpack_from('<H', data, 18)[0] == 106, "Expected Blackfin ELF")
    table = struct.unpack_from('<I', data, 32)[0]
    stride, count, names_index = struct.unpack_from('<HHH', data, 46)
    require(stride == 40 and 0 < count < 4096 and names_index < count and
            table + count * stride <= len(data), "Invalid ELF section table")
    headers = [struct.unpack_from('<10I', data, table + i * stride) for i in range(count)]

    def contents(h):
        if h[1] == 8:
            return b''
        require(h[4] + h[5] <= len(data), "ELF section exceeds file")
        return data[h[4]:h[4] + h[5]]

    def string(strings, index):
        require(index < len(strings), "ELF string index outside table")
        end = strings.find(b'\0', index)
        require(end >= index, "Unterminated ELF string")
        return strings[index:end].decode('ascii')

    names = contents(headers[names_index])
    sections, symbols = {}, {}
    for h in headers:
        name = string(names, h[0])
        require(name not in sections, "Duplicate ELF section")
        require(not (h[1] in (4, 9) and h[5]), "Unresolved ELF relocations")
        sections[name] = dict(type=h[1], flags=h[2], address=h[3], size=h[5], data=contents(h))
        if h[1] != 2:
            continue
        require(h[6] < count and h[9] == 16 and h[5] % 16 == 0, "Invalid ELF symbol table")
        strings = contents(headers[h[6]])
        for pos in range(0, h[5], 16):
            index, value, size, info, other, section = struct.unpack_from('<IIIBBH', contents(h), pos)
            name = string(strings, index)
            if name:
                require(section != 0, 'Undefined symbol: ' + name)
                symbols[name] = dict(value=value, size=size, type=info & 15)
    return sections, symbols
