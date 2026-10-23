# OP-XY 1.2.0 firmware contract

How the SDK integrates machines into stock OP-XY OS 1.2.0. This is a
reverse-engineered, version-bound contract for SDK maintainers, not a
manufacturer ABI; machine authors need only the [engine API](api.md).

[The firmware profile](../profiles/opxy-1.2.0.json) is the single source
both the Python SDK and the browser builder read: stock and tool hashes, the
reservation and its table bytes, identity ranges, stock catalog insertion
offsets and every edit. Heap and table edits carry their replacement bytes; a
hook names the module symbol it calls or jumps to, and each build computes and
verifies its bytes. The builder pins the profile digest. Stock
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
| Drum-page services | 14 | Routes controls, octave publication, assignment and waveform projection for machines declaring pad settings or drum controls |
| Recorder | 6 | Recognizes owned sample engines when the stock recorder selects, releases and saves a pad, and assigns completed recordings to owned pads |
| Relocated tables | 13 | Moves the engine records (63) and screen slots (128) into the last 4 KiB of the reservation |
| Screen order | 1 | Paints a selected owned synth page before stock overlays |
| Synth controls | 2 | Lets an encoder press on an owned synth's page select an alternate parameter, which its turns then edit |
| Startup label | 1 | Shows `OPEN 0.0.1-1.2.0` at boot through the stock startup text renderer |
| Module | 1 record | One loader block holding the linked module |

Everything else must reconstruct byte for byte. Protected ranges in
[`pipeline.py`](../opxy_sdk/pipeline.py) admit only hooks into the module and
the reviewed startup label.
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

The startup and catalog glue is C++ generated per collection
([`startup.cpp.in`](../sdk/platform/opxy-1.2.0/startup.cpp.in)); the checks are
[`registration.cpp`](../sdk/platform/opxy-1.2.0/registration.cpp), bound to the
stock tables in `registration_stock.cpp.in`. The two initializer hooks jump
into the middle of stock functions, so
[`startup_exit.s`](../sdk/platform/opxy-1.2.0/startup_exit.s) calls the C++
and then completes the stock epilogue it replaced.

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
plus an SVG asset named after the machine. The SDK screen shell
([`screen.hpp`](../sdk/platform/opxy-1.2.0/screen.hpp)) supplies the four
control titles and values that stock fills in. The machine's artwork
supplies the rest. Two display contracts exist, each sized by the machine's
declaration (see the [display API](display.md)):

- **Drawing:** mutable outlines, transformable nodes and a palette, updated
  with Q10 coordinates and matrices.
- **Segments:** 14-segment characters, a lit/unlit palette, one label and text
  in place of chosen control values.

Stock paints the screen slots in ascending page order each frame, so page
numbers are layers. The compositor's loop advance is hooked: when the selected
page is an owned synth's, it is painted right after slot 0, beneath stock
overlays such as the octave indicator. Every other slot keeps its order and
page IDs are unchanged.

The stock SVG parser **asserts (halts) on a number with five or more decimal
places**, and parses exponents on a separate, unverified path. Every authored
asset is limited to at most four decimal places and no exponents.

### Alternate controls

Tracks 0..7 show the instrument track controller (GUI screen 0, vtable
`0x8400b208`); tracks 8 and up use another controller. Its page word
`0x08023c74` is 0 on the engine page. An unshifted turn of encoder `e` there
edits parameter `e` of the selected track through `0x8d5ab8ec` (call site
`0x8c0b210a`), which owns stepping, parameter locks and publication; shifted
turns edit `4 + e`, and other pages edit 8 and up. The engine page's
parameters are the first eight words of the vector the voice renders. The
GUI key dispatcher `0x8c0b6670` passes the click of encoder `e` (key `10 + e`,
released without a turn and without shift) to `0x8d51e634(e)` before the top
controller, whose engine page ignores it.
[`synth_controls.cpp`](../sdk/platform/opxy-1.2.0/synth_controls.cpp) replaces
both calls: while the engine page shows an owned synth with
[alternates](api.md#alternate-controls), a press moves the position to its next
parameter slot and a turn edits that slot. For owned synths, Shift's indices
4..7 map back to the same shown positions; continuous controls receive a copy
of the three-word event with signed word 0 divided by ten. Words 1 (detents)
and 2 (acceleration) stay intact. Stock consumes the event synchronously and
still owns lock editing and publication. The selection is GUI state per track,
reset when the track's engine changes. Other pages and unowned engines retain
stock routing.

The auxiliary-track controller already folds Shift into positions 0..3.
Its call at `0x8c090636` uses the same fine scaling only for owned FX on tracks
14/15, checked against the FX registry rather than the synth registry.
The stock held-key getter `0x8d5b5ef4(10 + encoder)` supplies the sample
callback's held-turn flag. Encoder turns clear the separate pending-click
flag, so a press-and-turn does not also click on release.

Stock draws each position's title from the engine record's parameter-name
callback and its value as a percentage of the vector word. The screen's
parameter-vector getter (`0x8d4d7c60`) takes the selected track in R0; the
adapter passes it explicitly after refreshing alternate-control selection.
The adapter's callback names the shown parameter, and the screen shell passes stock a copy
of the vector with each position's shown word in place. Generated metadata
then supplies one-decimal percentage and bounded positive anchor-ratio
captions on custom synth screens; enums and machine text overrides remain
discrete. FX pages retain their stock captions.

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
ID checks. One generated table describes the collection's sample machines
([`sample_callbacks.cpp.in`](../sdk/platform/opxy-1.2.0/sample_callbacks.cpp.in));
[`sample_machines.cpp`](../sdk/platform/opxy-1.2.0/sample_machines.cpp)
admits an ID only while its registration is still ours, and an owned engine
borrows the multisampler payload. Track and voice IDs stay unchanged. Stock,
absent and conflicting registrations follow the original paths. Adding a
sample machine adds no firmware patch sites.

The stock note-start callback for these registrations is vtable offset +16;
factory creation alone does not start or choke a voice. Page 7 maps notes to
the stock 24 canonical pads. Optional same-key choke is scoped to track and
canonical pad, and checked before DSP or analysis lookup.

### Hooks

Hooks that replace a CALL are C++ with the C ABI. Hooks entered inside a stock
function are tiny assembly stubs: they save everything compiled C++ may
clobber through one routine pair ([`hook.s`](../sdk/platform/opxy-1.2.0/hook.s):
R0-R3, P0-P2, ASTAT, the I/M/B/L registers, both hardware loops and both
accumulators), call C++, and replay or deliver what stock expects. Stubs remain
only where the contract is not C: an argument in R5, outputs in R5/R7/P4/CC, a
return-address marker, the caller's frame, and replayed instructions.
Stock addresses used by more than one unit are in
[`stock.hpp`](../sdk/platform/opxy-1.2.0/stock.hpp); every sample record
offset is in [`stock_sample.hpp`](../sdk/platform/opxy-1.2.0/stock_sample.hpp).

### Sample analysis

The analysis service owns preparation, allocation and reclamation; the audio
callback only reads published data. Entries are keyed by sample object and
engine. The GUI marks assigned paths of analysis machines through the cache
message's priority byte, which carries only "assigned", so the file worker
prepares each such sample for every registered analysis machine, each within
its own budget. Browser page 4 suppresses new requests: stock auditions
replace regions while it is open. Results are released before stock frees the
PCM object.

### Pad settings and the drum page

Pad settings occupy the stock pad record's fade word as a tagged 16-bit value,
padded to survive stock's integer/float serialization. For a machine with pad
settings the drum bridge owns that word: stock does not paint a fade, the
Shift encoders 2/3 never reach stock, and presses never enter stock's mode
cycle. With drum controls they reach the machine instead. Unowned
registrations delegate to stock.

The assignment bridge validates worker generation, track, key and frame count
before supplying file metadata to `sample_assign`, then initializes the owned
region over the full loaded sample and restores the replaced pad's pitch,
reverse and volume before stock publishes it. A completed recording takes the
same path when the recorder initializes its region, with `recorded` set, the
recorder's frame count and 44.1 kHz rate, and no file metadata; it never
consumes the file worker's pending metadata. The stock loader's 882,000
decoded-frame cap still applies. Assignment looks up the raw note once and
stores the canonical key through the owned initializer hook, avoiding a
second octave conversion.

The drum page paints a temporary copy of the pad record: the machine's
effective pitch and play mode, never the saved tuning, markers or reverse. A
local GUI parameter vector keeps stock from adding the live pitch offset twice;
the original vector still drives stock's waveform trim overlays. Owned pages
show the outer markers. The live/step editor's pitch classification also
recognizes owned drum-page machines, so parameter zero uses stock's ten-cent
stepping and lock handling. Saved pad pitch uses the same step, stored in
stock root/fine fields and published through the existing region handler.

The sample adapter reads track transpose from the stock per-track audio
parameter table using stock note-start's 73-position mapping to -36..36
semitones, separately from pitch increments, which also include absolute note
pitch and modulation. Drum-key routing passes stock's track octave to its key
mapper and publishes the octave in a per-track word; the octave setter also
publishes each change. Audio maps notes with that snapshot and the same
integer mapping, without calling GUI project or pattern getters. Choke uses
the canonical pad; the raw note minus the canonical pad is `drum_transpose`.

## Send effects

Effects live in a separate 19-entry registry. Stock constructs an effect in
place inside the FX slot's **480-byte** storage on the audio thread, calls
`init`, then `process(left, right, parameters)` once per 64-sample block on
in-place stereo buffers. **No destructor ever runs**, so an effect may hold no
resources. The first slot word is the object's method table, which leaves 476
bytes of effect state.
