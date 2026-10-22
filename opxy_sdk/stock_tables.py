"""Relocated engine-record and screen-slot tables for exact stock OP-XY 1.2.0.

The static audit (docs/abi-1.2.0.md, "Relocated tables") found every direct
reader of the two tables: seven engine-record base loads, the engine validity
bound and clear length, the two screen-slot base loads in the slot getter and
the three 81-slot loop bounds. The relocated profile rewrites only those
immediates; this module decodes them independently of the profile's bytes.
"""
import struct

from .formats import require

STOCK_ENGINE_RECORDS, STOCK_ENGINE_COUNT = 0x846ea2e8, 33
STOCK_SCREEN_SLOTS, STOCK_SCREEN_COUNT = 0x84ebbfc0, 81
ENGINE_RECORDS, ENGINE_COUNT = 0x8d4cff60, 63    # 63 is the largest validity bound imm7 encodes
SCREEN_SLOTS, SCREEN_COUNT = 0x8d4cfd60, 128
RESERVATION_END = 0x8d4d0d60
RECORD_BYTES = 48
# Stock "none" values: the resolver/preset/GUI sentinel and the dispatcher's
# no-screen value. Their record and slot are never registered.
ENGINE_SENTINEL, PAGE_SENTINEL = STOCK_ENGINE_COUNT, STOCK_SCREEN_COUNT

# (site, kind, stock value, relocated value)
EDITS = (
    *[(site, 'imm32', STOCK_ENGINE_RECORDS, ENGINE_RECORDS) for site in
      (0x8d504c42, 0x8d504cee, 0x8d504d16, 0x8d505eda, 0x8d506192, 0x8d506624, 0x8d50684e)],
    (0x8d504d06, 'imm7', STOCK_ENGINE_COUNT, ENGINE_COUNT),
    (0x8d50618c, 'imm16', STOCK_ENGINE_COUNT * RECORD_BYTES, ENGINE_COUNT * RECORD_BYTES),
    *[(site, 'imm32', STOCK_SCREEN_SLOTS, SCREEN_SLOTS) for site in (0x8d51fbca, 0x8d51fc00)],
    *[(site, 'imm16', STOCK_SCREEN_COUNT, SCREEN_COUNT) for site in (0x8d51fcf6, 0x8d520176, 0x8d5208fc)],
)
SIZES = dict(imm32=8, imm16=4, imm7=2)


# Template values for the generated registration/readiness/page code.
REGISTRATION = dict(ENGINE_RECORDS='%#x' % ENGINE_RECORDS, ENGINE_LIMIT=str(ENGINE_COUNT),
                    SCREEN_SLOTS='%#x' % SCREEN_SLOTS, PAGE_LIMIT=str(SCREEN_COUNT))


def check_assignment(engine_id, page_id):
    """IDs a relocated build may register: in range, never the stock sentinels."""
    require(type(engine_id) is int and 0 < engine_id < ENGINE_COUNT and engine_id != ENGINE_SENTINEL and
            type(page_id) is int and 0 < page_id < SCREEN_COUNT and page_id != PAGE_SENTINEL,
            'Engine/page ID outside the relocated tables or equal to a stock sentinel')


def decode(kind, raw):
    """Return (opcode bits, immediate) for one of the three rewritten forms."""
    require(len(raw) == SIZES[kind], 'Unexpected instruction size')
    if kind == 'imm32':  # Blackfin+ Dreg/Preg = imm32
        opcode, high, low, zero = struct.unpack('<4H', raw)
        require(opcode & 0xffc0 == 0xda00 and zero == 0, 'Expected 32-bit immediate load')
        return opcode, high << 16 | low
    if kind == 'imm16':  # Dreg/Preg = imm16 (X)
        opcode, value = struct.unpack('<2H', raw)
        require(opcode & 0xffc0 == 0xe100, 'Expected 16-bit immediate load')
        return opcode, value
    (word,) = struct.unpack('<H', raw)  # Dreg = imm7 (X)
    require(word & 0xfc00 == 0x6000, 'Expected 7-bit immediate load')
    value = word >> 3 & 0x7f
    return word & ~(0x7f << 3), value - 0x80 if value & 0x40 else value


def check_edits(patches, base=7):
    """The reviewed hook and heap edits first, then exactly the table edits."""
    require(len(patches) == base + len(EDITS), 'Unexpected table edit count')
    for patch, (site, kind, stock, relocated) in zip(patches[base:], EDITS):
        require(int(patch['address'], 16) == site and patch['length'] == SIZES[kind], 'Unexpected table edit site')
        before, after = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
        opcode, value = decode(kind, before)
        require(value == stock, 'Table edit preimage differs from audited stock value')
        require(decode(kind, after) == (opcode, relocated), 'Table edit must change only the immediate')
