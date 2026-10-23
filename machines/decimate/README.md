# Decimate send effect

A sample-and-hold rate reducer with a crossover, output tone filter and
additive dry level. The original hold timing and unquantized samples are
preserved: with Xover at zero, Tone fully open and Dry at zero, the return
is bit-for-bit identical to the original Rate/Mix version at fully wet.

| Encoder | Control | Mapping |
|---|---|---|
| 1 | Rate | Hold length 1-32 samples; higher settings reduce the update rate |
| 2 | Xover | Zero processes the full band; raising it selects higher frequencies for the effect |
| 3 | Tone | Softens the crushed signal after sample-and-hold; fully open by default |
| 4 | Dry | Adds untouched input at zero to unity gain, without reducing the processed signal; zero by default |

## Using it as a send

Start with Xover at zero, Tone at 100 and Dry at zero for the original
full-band sound. Use the track sends and FX return level to set how much
Decimate you hear. Raise Xover to keep bass out of the effect's input while
crushing the upper frequencies. Lower Tone to tame the resulting high-frequency
fizz. Dry adds clean signal to the return independently of the effect.

This follows the separate dry-level convention described for stock delay and
reverb in the [OP-XY FX guide](https://teenage.engineering/guides/op-xy/fx).
Dry is not a crossfade: turning it up does not turn the crushed sound down.
The main mix's existing dry track is unaffected. With Dry at zero, the low
band removed by Xover is not added back to this send return; it remains
available through the normal dry track.

## Crossover and tone

Xover uses a gradual first-order (6 dB/octave) high-pass derived from a
complementary low/high split. Its normalized readout maps approximately to
`10000 * (value / 100)^2` Hz at 44.1 kHz:

| Xover readout | Approximate crossover |
|---|---|
| 0.0 | Full band / crossover off |
| 10.0 | 100 Hz |
| 25.0 | 625 Hz |
| 50.0 | 2.5 kHz |
| 75.0 | 5.6 kHz |
| 100.0 | 10 kHz |

The upper band is held at the selected Rate, then passes through Tone's
one-pole low-pass. Tone runs from approximately 200 Hz at zero to exact
bypass at 100. The untouched input is added afterwards at the Dry level.
Neither Xover nor Tone filters the Dry path. Sample-rate reduction can create
aliases below the crossover; Xover is not an output high-pass.

Both filter coefficients use roughly 1.5 ms smoothing time constants.
Returning Xover to zero and Tone to 100 restores the exact original wet path
once the coefficients settle. Full-scale peaks saturate instead of wrapping,
including when adding dry signal. No bit-depth reduction, jitter or automatic
gain compensation is applied. Shift + turn gives fine adjustment of all four
controls. The FX page retains stock value captions.

## Saved sounds

Control order is now Rate, Xover, Tone, Dry. Saved settings and locks from
Rate/Bits/Jitter/Mix are not migrated: the former Bits value becomes Xover,
Jitter becomes Tone, and Mix becomes Dry. Only Rate retains its meaning.
The earlier two-control version's Mix slot also becomes Xover. Reset these
controls and their locks when revisiting older sounds. The new defaults are
Rate 25, Xover 0, Tone 100 and Dry 0.

## Implementation

`fx.cpp` implements the [effect interface](../../docs/api.md#effects):
`initialize` and `process` over one 64-sample block with no allocation, I/O or
stock calls. Filtering uses a small coefficient table and 32-bit integer
arithmetic. `core.h` declares the 44-byte `State`. `machine.json` declares FX
ID 11. It is part of the collection that `python sdk.py build` links (see
[native builds](../../docs/build.md)).
