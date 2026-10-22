# OP-XY 1.2.0 firmware contract

How the SDK integrates machines into stock OP-XY OS 1.2.0. This is a
reverse-engineered, version-bound contract for SDK maintainers, not a
manufacturer ABI; machine authors need only the [engine API](api.md).

Stock and tool hashes, every edited byte and the reservation live in
[the firmware profile](../profiles/opxy-1.2.0.json). Stock
addresses live beside the code that uses them: the adapter templates in
`sdk/platform/opxy-1.2.0/`,
[`stock_tables.py`](../opxy_sdk/stock_tables.py) and
[`firmware.py`](../opxy_sdk/firmware.py). This page says what they mean.

## What a build changes

The input is decrypted stock `os.ldr` 1.2.0
(`e9dbdaa1…98f2`, pinned in the profile). An encrypted `.tfw` or any other
version is rejected. The output differs from stock in exactly these places:

| Change | Edits | Purpose |
| --- | --- | --- |
| Reservation | 2 | Shrinks the application heap by 512 KiB; the module lives in the freed tail |
| Hooks | 5 | Branches from the synth initializer, both screen factories and both catalog-insertion calls into SDK startup code |
| Sample dispatch | 2 | Recognizes owned SDK sample registrations and selects the stock multisampler audio payload |
| Sample analysis | 10 | Schedules bounded background work, snapshots committed assignments, releases cached analysis and reports progress |
| Drum-page services | 14 | Routes controls, octave publication, assignment and waveform projection for machines declaring drum controls |
| Relocated tables | 14 | Moves the engine records (63) and screen slots (128) into the last 4 KiB of the reservation |
| Startup label | 1 | Shows `OPEN 0.0.1-1.2.0` at boot through the stock startup text renderer |
| Module | 1 record | One loader block holding the linked module |

Everything else must reconstruct byte for byte. Protected ranges in
[`pipeline.py`](../opxy_sdk/pipeline.py) admit only the exact authenticated
sample-page edits in [`sample_hooks.py`](../opxy_sdk/sample_hooks.py).
The bootloader is never modified.

## Startup

1. The synth initializer's exit registers every effect, then, on the audio
   role, every synth and sample engine.
2. On the GUI role, a synth registers only after its screen is ready: the
   screen factory exit constructs it and checks its loaded artwork.
3. The catalog adapter admits a machine's menu entry only while its engine
   record and screen are owned and ready, and delegates every other name to stock.

Registration is checked: the record must be empty or already ours, and the
name map must not point elsewhere. The stock initializer clears and refills the
records on every run, so registration is re-checked each time rather than cached.

## Identities

| Table | Size | Never use | Notes |
| --- | --- | --- | --- |
| Engines | 63 (relocated) | 33 (stock "none"), IDs stock registers | IDs above 32 exist only with the relocated tables |
| Screen pages | 128 (relocated) | 81 (stock "none") | Sample engines show stock page 2 or 7 instead |
| Effects | 19 (stock) | IDs stock registers | Free IDs: 1–4, 6–8, 11; all effects use page 21 |

Presets store the engine **name**. Projects store the engine **number**.
Firmware without the relocated tables opens a project that uses an engine above
32 with Prism (18) instead. Published IDs therefore never change.

## Synth voices

Stock asks the factory for a voice object per voice index (0–255) and calls
it through an 11-entry method table: render once per 64-sample block, start on
a note, and unchanged stock defaults for the rest (see
[`voice.cpp.in`](../sdk/platform/opxy-1.2.0/voice.cpp.in)). One adapter serves
every synth.
Render receives 64 output words and 8 parameter words. The SDK adds the stock
per-sample pitch increments. Output is mono Q31 at half-scale peak. Stock
velocity, envelope, filter and mixing run afterwards.

## Screens

A synth's page is a stock screen object: 76 stock bytes, plus adapter state,
plus an SVG asset named after the machine. The SDK screen shell supplies the
four control titles and values that stock fills in. The machine's artwork
supplies the rest. Two display contracts exist, each sized by the machine's
declaration (see the [display API](display.md)):

- **Drawing:** mutable outlines, transformable nodes and a palette, updated
  with Q10 coordinates and matrices.
- **Segments:** 14-segment characters, a lit/unlit palette, one label and text
  in place of chosen control values.

The stock SVG parser **asserts (halts) on a number with five or more decimal
places**, and parses exponents on a separate, unverified path. Every authored
asset is limited to at most four decimal places and no exponents.

## Sample engines

Stock's sampler, multisampler, drum and drumline engines are synth
registrations with record flag 1. Before calling such an engine's factory, the
voice allocator acquires the track's cached sample and publishes it in a global
that the factory reads. The SDK registers sample engines the same way and
passes the sample as a read-only `opxy::SampleView`: 16-bit PCM in RAM, frame
count, rate and channel layout. Tempo, tick position and play state come as an
advisory `opxy::Transport`. Sample selection uses the stock sample page.

Sample engines declaring stereo output write 64 interleaved L/R frames to
the stock 128-word scratch buffer. Vtable offset +32 returns 1 to select the
stock stereo mixer; mono declarations retain 64-word output and return 0.
The stock stereo PCM reader consumes packed left/right 16-bit pairs, while
its output writes alternating 32-bit left/right words.

Requirements: flag 1, an engine ID of 34–62, and page 2 or 7. The engine never
touches the sample cache or its lock.

Stock's sample predicate and note-region dispatcher also have explicit engine
ID checks. The SDK generates their adapters from the collection: each candidate
ID must pass its registration ownership check before borrowing the multisampler
payload. Track and voice IDs stay unchanged. Stock, absent and conflicting
registrations follow the original paths. These shared boundaries are part of the
platform profile; adding a sample machine does not add firmware patch sites.

The stock note-start callback for these registrations is vtable offset +16;
factory creation alone does not start or choke a voice. Page 7 maps notes to
the stock 24 canonical pads. Optional same-key choke is scoped to track and
canonical pad, and checked before DSP or analysis lookup.

The optional analysis service owns preparation, allocation and reclamation.
The audio callback only reads published data. Browser page 4 suppresses new
analysis requests. The assignment bridge validates worker generation, track,
key and frame count before supplying filename metadata to the assignment
callback. The callback also receives the replaced pad's saved settings.
Custom drum-page assignments span the full loaded sample; replacements retain
saved pitch, reverse and volume before stock publishes the new region.

The shared drum bridge stores a tagged 16-bit machine setting in the region's
fade word, with padding to survive stock's integer/float serialization. It
suppresses stock fade painting for owned custom pages and projects machine
effective pitch/play state through a temporary region copy. The panel receives
the same live parameter values as audio. A local GUI vector prevents stock
from adding the already-applied pitch offset twice; the original vector still
drives stock waveform trim overlays. Live encoder and automation dispatch
remain stock-owned. Stock reverse, volume and
waveform graphics remain stock-owned. Untagged data is migrated by the
machine's C++ callback. Unowned registrations delegate to stock. The bridge
does not extend the stock loader's 882,000 decoded-frame cap.

The live/step editor's pitch classification also recognizes owned drum-page
machines, so parameter zero uses stock's ten-cent stepping and lock handling.
Other parameters retain their original editing paths and engine identity.
Saved pad pitch uses the same ten-cent step, stored in stock root/fine fields
and published through the existing region handler. Machine settings do not
store pitch; the display adds saved region tuning to the panel's live offset.
The sample adapter reads track transpose from the audio parameter table
(`0x84eb3bc8`, stride `0xe8`, offset `0xd0`) using stock note-start's
73-position mapping to -36..36 semitones. It supplies this separately from
pitch increments, which also include absolute note pitch and modulation.
Drum-key routing passes stock's track octave (`0x8d58da64`) to its key mapper
(`0x8d5b6800`) and publishes the octave in an aligned per-track word. Audio
uses that snapshot with the same integer mapping, without calling GUI
project/pattern getters. The stock octave setter also publishes each change
immediately; playback can reuse a sample without another GUI lookup.
Voice choke uses that canonical pad; the raw note minus
the canonical pad supplies a separate octave pitch offset captured at start.
Assignment looks up the raw note once and stores the canonical key through
the existing owned initializer hook, avoiding a second octave conversion.

## Send effects

Effects live in a separate 19-entry registry. Stock constructs an effect in
place inside the FX slot's **480-byte** storage on the audio thread, calls
`init`, then `process(left, right, parameters)` once per 64-sample block on
in-place stereo buffers. **No destructor ever runs**, so an effect may hold no
resources. The send-buffer sample scale has not been established.

## Device status

| Build | Status |
| --- | --- |
| 2op FM + Macro Osc, relocated tables (2op at engine 34) | Ran on a device with the earlier object layout; the current layout needs a retest |
| Decimate (FX 11) | Not yet tried on a device |
| Timestretch (engine 35, drum page) | Earlier implementations ran on a device; the current shared-service implementation needs device qualification |
| Startup label, bundled presets | Not yet observed on a device |

Host checks establish byte-exact reconstruction and bounded static properties.
They do not establish timing, audio behaviour or recovery.
