# Decimate send effect

A sample-and-hold rate reducer, the first curated send effect. It never
rescales samples, so it behaves the same whatever the stock send-buffer scale
turns out to be.

| Knob | Mapping |
|---|---|
| rate | Hold length 1–32 samples |
| mix | Dry to wet (Q15 crossfade); the catalog default is fully wet |

`fx.cpp` implements `init` and `process` over one 64-sample block with no
allocation, I/O or stock calls; `core.h` declares the state, which the SDK
places in the stock 480-byte effect slot. `machine.json` declares its stock
name and FX ID 11. It is part of the collection that `python sdk.py build` links
(see [native builds](../../docs/build.md)).
