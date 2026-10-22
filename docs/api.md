# Engine API

A synth supplies `definition.json`, `engine.cpp`, state headers and a display.
The [first-machine walkthrough](first-machine.md) creates a standalone source
directory and previews it without native integration.
Use [2op FM](../machines/fm2op/engine.cpp) for a small oscillator or
[Macro Osc](../machines/macroosc/engine.cpp) for state shared between voices. SDK adapters own allocation, C linkage and stock registration.

## Platform rules

These come from the stock firmware, not from SDK convention. Breaking one
fails the build or, for the artwork rule, halts the device's SVG parser.

| Area | Rule |
| --- | --- |
| Machine folder | C++ source, definition JSON, `machine.json` and artwork only. No build scripts, generators or tests |
| C++ | Freestanding C++11: no exceptions, RTTI, static constructors, allocation, OS headers, `#if`, inline assembly or platform macros |
| Callbacks | Bounded work per 64-sample block; no blocking, logging, file access or graphics from audio callbacks |
| Synth controls | Exactly four controls; values arrive as Q31 and the stock menu stores Q15 defaults |
| Audio | 64 frames at 44.1 kHz, Q31 output at half-scale peak; mono by default, optional stereo for sample engines |
| Identity | Stock name ≤ 15 characters; engine IDs come from the free table entries and own screen pages from 82–127; they never change once published. Engine 33 and page 81 are reserved |
| Sample engines | Engine ID 34–62, stock sample page 2 or 7; the sample is read-only and borrowed for the voice's lifetime |
| Effects | State fits in 476 bytes, holds no resources (no destructor ever runs) and uses a free FX ID on page 21 |
| Artwork | At most four decimal places and no exponent notation in any number; explicit paint on every leaf; no `style`, events or external references |

The [firmware contract](abi-1.2.0.md) explains where each rule comes from.

## Memory and limits

Every selected machine and the SDK share **one 508 KiB module region**: code,
constant data and zero-initialized state together. It is the 512 KiB the
firmware reserves from its heap, minus 4 KiB of relocated stock tables. There
is no per-machine allowance: a build that does not fit names each machine's
share, and `sdk.py compile` and the builder's memory meter report the same
figures. State usually dominates, since a synth's voice pool is
`voiceBytes × voiceCapacity`.

| Limit | Value | Why |
| --- | --- | --- |
| Module memory | 508 KiB for the whole collection | Firmware heap reservation minus the relocated tables |
| Voices | 1..256 per machine | Stock voice indices |
| Effect state | 476 bytes | Size of the stock effect object |
| Synth controls | Exactly 4 | The stock four-knob page |
| Sample and effect controls | 1..8 | The stock eight-word parameter vector |
| Control labels | 8 characters | The stock parameter page |
| Engine IDs, screen pages | 34–62, 82–127 | Free entries of the relocated stock tables |
| Drawing shape | ≤ 4 paths of ≤ 64 points, ≤ 64 nodes, ≤ 16 palette entries | Fixed-size renderer object and frame |
| Segment display | 1..8 characters, 0..3 glow layers, 0..4 dials | Immediate offsets in the native renderer |

`voiceBytes`, `sharedBytes` and display state have no limit of their own
beyond whole words and module memory. Browser previews run 8 voices in
512 KiB of WebAssembly memory; a machine that needs more still builds for the
device.

## Definition

Every machine kind keeps its controls in `definition.json` (for example
[2op FM's](../machines/fm2op/definition.json)); the
[validator](../opxy_sdk/definitions.py) rejects missing or unknown fields.

| Field | Contract |
| --- | --- |
| `schema` | 1 |
| `id`, `name`, `cppNamespace` | Machine identity, display name and C++ namespace |
| `parameters` | Ordered controls, each with `id`, `label`, `default`, `mapping`, `display`: four for a synth, one to eight for a sample engine or effect. Labels are at most eight letters, digits or spaces |
| `presets` | Named maps containing exactly the declared controls; may be empty |
| `resources` | What the kind declares about its storage (below) |

Controls are finite numbers in [0, 1]. Mappings support increasing `anchors`,
`power` (`maximum * value^exponent`), `exponential` (`minimum *
(maximum/minimum)^value`) and `enum`. Display formats are `ratio`, `percent`,
`duration` and `enum`. Enum quantization matches the native Q31-to-Q15 path.
Parameter order and mapping changes affect saved sounds. The stock parameter
page shows labels in lower case.

A sample engine declares `voiceCapacity` (1..256), optionally `sampleAnalysis`
(its analysis heap budget in bytes; see below), and optional integer flags
`chokeSameKey`, `drumControls` and `stereoOutput` (0 or 1; omitted means 0).
`drumControls` requires stock page 7. An effect declares no resources (`{}`).
A synth declares:

| Field | Required value or meaning |
| --- | --- |
| `voiceBytes`, `voiceAlignment` | `Voice` size (whole words) and alignment, checked against the compiled type |
| `voiceCapacity` | Voices the firmware may create, 1..256 |
| `sharedBytes` | `Shared` size, or 0 when `Shared` is empty |
| `blockFrames`, `sampleRate` | 64 frames, 44100 Hz |
| `outputPeakQ31` | Positive declared oscillator peak; the preview uses it for audition gain |
| `display` | The screen's kind and shape; see the [display API](display.md) |

The SDK never runs constructors or destructors for `Voice`, `Shared` or
`DisplayState`: their storage starts zeroed and the callbacks set it up.
Exceptions and allocation are not supported.

## Audio buffers and ownership

[opxy/audio.hpp](../sdk/include/opxy/audio.hpp) defines the callback types.

| Argument | Contract |
| --- | --- |
| Voice state | SDK-owned, correctly aligned storage; the engine initializes all sound fields |
| `Output` | Writable 64-word mono signed Q1.31 buffer; write every sample |
| `Parameters` | Read-only normalized Q31 words; the first four are the declared controls |
| `Pitch` | Read-only 64-word unsigned phase-increment buffer, modulo 2^32 cycles |

Pointers are non-null, aligned and non-overlapping. Do not retain borrowed
buffer pointers beyond the call. `round(normalized * 2147483647)` produces a
control word. Physical units are the engine's mapping, not the buffer format.
Use [Q31 helpers](../sdk/include/opxy/q31.hpp) for defined multiply/rounding;
phase arithmetic wraps instead of saturating like audio.

Callbacks perform bounded work without allocation, blocking, file access,
logging or graphics. Device amplitude envelopes, filters and mixing follow the
oscillator callback; the browser supplies a simpler audition gate and mixer.

## Lifecycle

Every synth implements four callbacks in its declared namespace:

```cpp
struct Voice { ... };   // one voice's state
struct Shared { ... };  // state shared by every voice; empty when nothing is shared

void initialize(Voice& voice, Shared& shared, opxy::u32 owner);
void start(Voice& voice, Shared& shared, opxy::u32 owner);
void destroy(Voice& voice, Shared& shared, opxy::u32 owner);
void render(Voice& voice, Shared& shared, opxy::u32 owner,
            opxy::Output output, opxy::Parameters parameters, opxy::Pitch pitch);
```

Storage begins zeroed; `owner` is a stable nonzero voice ID. `initialize` runs
when the firmware creates the voice and establishes all sound state; `start`
runs on each note; `destroy` releases anything the voice holds in `Shared`.
Callbacks run serially per voice. The browser preview's voice stealing and
panic use the same lifecycle. The SDK adapter owns the firmware object header,
method table and voice pool; none of that belongs in `Voice`.

[LeasePool](../sdk/include/opxy/lease_pool.hpp) provides fixed typed resources.
`acquire` reuses an owned slot or clears the free/oldest slot; `get` verifies
ownership; `release` cannot free a stolen lease. The engine decides how a
voice behaves after losing a resource. This pool has no locks and requires
serialized access.

## Sample engines

[sample_engine.hpp](../sdk/include/opxy/sample_engine.hpp) defines the portable
sample interface. A sample machine supplies `sample.cpp` with these callbacks:

```cpp
void initialize(Voice&, const opxy::SampleView&);
void start(Voice&);
void render_sample(Voice&, const opxy::SampleBlock&);
```

The SDK retains the sample for the stock voice's lifetime. `SampleBlock` carries
the output and track parameter buffers, pitch increments, advisory transport,
clamped trim bounds, reverse and gain, legacy tuning/fade values, per-pad saved
settings and optional immutable analysis. A missing analysis pointer means
preparation is pending or unavailable. Never retain a block or its transient
buffers. Sample PCM and its analysis remain valid until the voice is destroyed.

`stereoOutput: 1` supplies 64 interleaved left/right frames (128 Q31 words)
and sets `SampleBlock.output_channels` to 2. Otherwise it supplies 64 mono
words and sets the field to 1. Write every supplied word, including silence.
Source channel count and output channel count are separate. Stock mixing
uses the declared output layout.

`sampleAnalysis: <bytes>` asks the SDK to prepare per-sample data with the
machine's own analysis, declared in
[sample_analysis.hpp](../sdk/include/opxy/sample_analysis.hpp): a measuring
pass sizes the storage, then a building pass fills it. The
SDK prepares committed assignments outside audio callbacks, each sample to
completion on the stock file worker, defers while the sample
browser is open, publishes completed immutable results and releases them before
the stock PCM object is freed. Storage is allocated from the stock heap, which
also holds samples, up to the declared budget (at most 2 MiB); a sample that
does not fit stays unanalyzed. One machine per collection may declare it.

`chokeSameKey: 1` silences earlier voices only when another note actually starts
on the same track and key. Page 7 uses the stock 24-pad canonical key mapping,
so octave aliases of a pad share ownership. Different pads and tracks are
independent. Stock envelopes and project voice settings still apply.

With `drumControls: 1`, the machine also implements:

```cpp
opxy::u32 sample_assign(const opxy::SampleAssignment&);
opxy::u32 sample_migrate(const opxy::SampleRegion&);
void sample_control(opxy::u32& settings, const opxy::SampleControl&);
void sample_panel(opxy::u32 settings, opxy::Parameters live, opxy::SamplePanel&);
```

Settings are a **16-bit** machine-defined value persisted per pad. Assignment
receives a bounded filename, loaded frame count, source rate, advisory tempo
and `previous` settings from an assigned pad being replaced. The machine chooses
which settings to retain and how new sample metadata overrides them. Empty or
untagged pads have uninitialized `previous` settings. The SDK retains a replaced
pad's saved pitch, reverse and volume; the new sample's trim spans its full length.
Migration supplies defaults for untagged regions. Control events identify a
zero-based encoder, direction, press and Shift state. The bridge routes main
encoder 4 and Shift encoders 2/3 to the machine. The SDK edits main pitch
in ten-cent steps over +/-12 semitones using stock root/fine fields; pressing
resets it. Stock owns main start/end trims and Shift reverse/volume.
The panel supplies a live pitch offset in cents, loop/play state
and two NUL-terminated Shift captions of at most 15 bytes. The panel receives
the eight normalized live Q31 parameters used for audio and returns effective
play mode and pitch offset. The SDK adds saved pitch (`6000 - root_cents`)
for display; audio receives the same saved tuning in `SampleRegion`. Stock paints a
temporary region copy; saved tuning, markers and reverse remain untouched.
`SampleBlock.track_transpose` supplies the track settings transpose in
semitones (-36 to +36), separately from the pad key and live pitch parameter.
`SampleBlock.key_transpose` supplies the drum note's octave displacement from
its assigned pad in semitones. It is captured at note start. Drum-page sample
lookup and same-key choke use the stock octave-aware 24-pad mapping.
Drum controls expose outer start/end bounds to playback; hidden inner loop
markers do not narrow that interval.
Callbacks must be bounded and allocation-free; they do not receive native
pointers or call stock graphics. See [Timestretch](../machines/timestretch/controls.h).

These per-pad settings are the base for the track's normalized live parameter
vector. Stock retains its live editing and automation routing. Drum-page
definitions use pitch/start/end/play in slots 0–3, reverse in slot 4, custom
Shift controls in slots 5–6 and volume in slot 7. Pitch and the bipolar trim
modifiers are neutral at 0.5; reverse is neutral at 0 and volume at 1.
Live pitch uses stock's -12 to +12 semitone offset range and ten-cent encoder
steps. The machine must apply its live controls to audio as well as its panel.
The platform combines live reverse and volume with the saved region for the
display; the machine applies the same values to playback. Play-mode and
custom Shift defaults are machine policy. `definition.json` supplies names
and preset defaults; the callbacks combine them with the pad's settings.

## Registration boundary

A machine's folder name is its stock name: the engine type the device lists,
its catalog and preset entries, its screen file and its symbol prefix. It is a
lowercase letter followed by letters, digits or `_`, at most 15 characters, and
may not be a stock engine or effect type or start with a reserved prefix
(`extensions`, `sdk`, `kit`, `stock`, `local`). `machine.json` declares only the
engine (or FX) and page IDs. Names and IDs are part of saved presets, so they
never change once published. The SDK rejects IDs that stock registers, the stock sentinels and
conflicts within the collection. Generated adapters check record/name ownership
and screen readiness before catalog admission; the packager authenticates
firmware and constrains writes. See [native builds](build.md).

Optional `presetDefaults: {"amp": {...}}` in `machine.json` overrides generated
factory preset envelope values. Allowed keys are `attack`, `decay`, `release`
and `sustain`, each an integer from 0 to 32767. It does not rewrite existing
projects or presets. Generated instrument presets use polyphonic voice mode.

Arbitrary external-engine loading is not implemented: a machine reaches the
firmware by joining the collection in `profiles/collection.json`.
