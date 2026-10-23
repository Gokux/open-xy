# Decimate send effect

A sample-and-hold rate reducer with a low cut, stereo capture offset and
additive dry level. With Low Cut, Stereo and Dry at zero, the return is
bit-for-bit identical to the original Rate/Mix version at fully wet.
The original unquantized samples and steady 1-32-sample hold timing remain.

| Encoder | Control | Mapping |
|---|---|---|
| 1 | Rate | Hold length 1-32 samples; higher settings reduce the update rate |
| 2 | Low Cut | Zero processes the full band; raising it removes bass before crushing |
| 3 | Stereo | Offsets right-channel captures by up to half the hold period; zero keeps both channels aligned |
| 4 | Dry | Adds untouched input at zero to unity gain without reducing the processed signal; zero by default |

## Using it as a send

Start with Low Cut, Stereo and Dry at zero for the original full-band sound.
Use the track sends and FX return level to set how much Decimate you hear.
Raise Low Cut to keep bass out of the crushed return. Turn up Stereo to spread
the crushed texture, then raise Dry if you want clean signal in the return too.

Dry follows the separate level convention described for stock delay and reverb
in the [OP-XY FX guide](https://teenage.engineering/guides/op-xy/fx). It adds
clean audio without turning the crushed signal down. The main mix's dry track
is unaffected. Bass removed by Low Cut is not added back to this send return;
it remains available through the normal dry track.

## Low Cut

A gradual first-order high-pass selects the upper band before sample-and-hold.
The normalized readout maps approximately to `10000 * (value / 100)^2` Hz
at 44.1 kHz:

| Low Cut readout | Approximate cutoff |
|---|---|
| 0.0 | Full band / filter off |
| 10.0 | 100 Hz |
| 25.0 | 625 Hz |
| 50.0 | 2.5 kHz |
| 75.0 | 5.6 kHz |
| 100.0 | 10 kHz |

The slope is 6 dB/octave. Sample-rate reduction can create aliases below the
cutoff; this is an input filter. Its coefficient has a roughly 1.5 ms smoothing
time constant. Turning Low Cut off returns to exact full-band processing once
the coefficient settles.

## Stereo

The left channel keeps the original capture clock. Stereo offsets the right
channel's captures by whole samples, from zero to half the current hold period
(rounded down for odd periods). Both channels still update at the same rate.
At a 32-sample hold, maximum Stereo offsets the right clock by 16 samples,
about 0.36 ms. At a one-sample hold, Stereo has no effect. Short holds have
fewer available offset steps.

Changes latch at the start of a left-channel hold cycle. Adjusting Rate or
Stereo can briefly shorten or lengthen a right-channel hold while the clocks
realign. At startup, the right wet channel waits for its first capture; at
maximum Rate/Stereo this is only 16 samples. Turning Stereo back to zero aligns
both clocks at the next left capture. The channels never feed into each other;
Stereo can spread mono material, and summing it back to mono can change its tone.
It does not pan or delay the Dry path. No jitter or bit-depth reduction is used.

Shift + turn gives fine adjustment of all four controls; Stereo still resolves
to whole-sample timing. The FX page retains stock value captions. Full-scale
peaks saturate instead of wrapping, including when adding Dry.

## Saved sounds

Control order is Rate, Low Cut, Stereo, Dry. Only Rate retains its meaning from
Rate/Bits/Jitter/Mix; the other slots are not migrated. The earlier two-control
Mix slot becomes Low Cut. In the previous Low Cut/Tone test build, the Tone slot
now becomes Stereo, so a saved fully open Tone becomes maximum Stereo. Reset
these controls and their locks when revisiting older sounds. New defaults are
Rate 25, Low Cut 0, Stereo 0 and Dry 0.

## Implementation

`fx.cpp` implements the [effect interface](../../docs/api.md#effects) entirely
in C++: `initialize` and `process` over one 64-sample stereo block, with no
allocation, I/O or stock calls. Filtering and timing use 32-bit integer
arithmetic. `core.h` declares a 36-byte `State`; the effect retains ID 11.
See [native builds](../../docs/build.md) for collection verification.
