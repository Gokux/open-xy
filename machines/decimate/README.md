# Decimate send effect

A sample-and-hold rate reducer. It holds and crossfades samples without
rescaling them, so its output keeps the send buffer's own scale.

| Knob | Mapping |
|---|---|
| rate | Hold length 1–32 samples |
| mix | Dry to wet (Q15 crossfade); the catalog default is fully wet |

`fx.cpp` implements the [effect interface](../../docs/api.md#effects):
`initialize` and `process` over one 64-sample block with no allocation, I/O or
stock calls. `core.h` declares the 12-byte `State`. `machine.json` declares FX
ID 11. It is part of the collection that `python sdk.py build` links (see
[native builds](../../docs/build.md)).
