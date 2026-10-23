# Decimate send effect

A sample-and-hold rate and bit-depth reducer. It holds, quantizes and
crossfades samples without rescaling them, so its output keeps the send
buffer's own scale.

| Knob | Mapping |
|---|---|
| rate | Hold length 1–32 samples |
| bits | Each held sample rounded to 1–16 bits; the default 16 is effectively clean |
| jitter | Each hold's length varies randomly by up to its own length, like an unstable sampler clock; 0 is steady |
| mix | Dry to wet (Q15 crossfade); the catalog default is fully wet |

Shift + turn adjusts rate, jitter and mix at one tenth of their normal rate;
bit depth stays discrete. The FX page retains its stock value captions.

`fx.cpp` implements the [effect interface](../../docs/api.md#effects):
`initialize` and `process` over one 64-sample block with no allocation, I/O or
stock calls. `core.h` declares the 20-byte `State`. `machine.json` declares FX
ID 11. It is part of the collection that `python sdk.py build` links (see
[native builds](../../docs/build.md)).
