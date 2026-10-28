# Firmware extensions

Extensions change controller and sequencer behavior. Machines implement sound
and display callbacks; extensions receive selected-track context, accepted live
notes, releases, scaled recording ticks and controls. Capture is the first
extension, in [`extensions/capture/`](../extensions/capture/extension.cpp).

An extension is ordinary C++11 compiled into the firmware. It has no firmware
addresses, assembly, platform conditionals or OS headers. The SDK installs each
authenticated hook once and forwards stock input unchanged. This interface is
experimental and source-level; it is not a dynamic loader or binary ABI.

## How the SDK exposes the firmware

Three layers, kept apart:

1. **Patch sites** are private and belong to one OS release: the addresses in
   [`profiles/opxy-1.2.1.json`](../profiles/opxy-1.2.1.json). The SDK owns every
   site, each exactly once. No extension or machine patches the firmware.
2. **Events** are public and outlive an OS release. The SDK turns each site into
   one named event. An OS port moves the sites; events stay the same.
3. **Subscribers** are extensions and machines. They declare the events they
   take and filter them; they never see a site.

### Name an event by where it happens

"Note on" is ambiguous: a note passes several stages, and each stage is its own
event. A subscriber that wants only one track filters the event; it does not
need another site.

| Stage | Happens when | Here |
| --- | --- | --- |
| Input note | A key or MIDI note arrives, before recording and the sequencer | `note_on` and `note_off` (live input stock accepted) |
| Sequencer note | A pattern step plays | Not exposed |
| Track note | Live and sequenced notes reach a track, before its instrument | Not exposed |
| Voice start | The instrument starts a voice | A machine's voice callbacks |

The same holds for time (transport tick, GUI tick), controls (keys, encoder
edits, page keys) and the project lifecycle (load, clear, save).

### Each event grants one kind of access

| Access | Rule | Here |
| --- | --- | --- |
| Observe | Read-only; any number of subscribers, in collection order | `context`, `note_on`, `note_off`, `tick`, `activity`, `control` |
| Transform | One ordered chain that may change or drop the event | None yet |
| Claim | One owner; a second claimant fails the build | Record double-tap (`record_double_tap`) |

### And states its thread and host

Each event says which thread it runs on: audio, GUI and controller, or project
load and save. Callbacks here run on the controller path. A subscriber is either
firmware-wide, as an extension, or hosted by a machine on a track, which filters
to that track for it.

### Four kinds of interface

| Kind | What | Here |
| --- | --- | --- |
| Events | Something happened | The callbacks below |
| Actions | Change something through stock | `Actions::insert_notes`, `Actions::notify` |
| Surfaces | Add to the screen | None for extensions yet: menu rows, pages, overlays |
| Saved state | Data kept with a project | None for extensions yet |

### Adding to the SDK

A new feature adds subscribers, not patch sites. A change that adds a patch site
names the event it creates, its stage, access, thread and host, and says why no
existing event serves. Each site belongs to a profile service and is applied
only to builds that use it.

Adjacent sites are still separate sites. The controller update that capture
observes follows stock's GUI tick in the same main loop; an event for that tick
would be a site of its own, beside this one.

## Add an extension

Create `extensions/<id>/extension.cpp`. Export
`opxy::extensions::<id>::hooks`, a constant
[`Hooks`](../sdk/include/opxy/extension.hpp) descriptor; unused callbacks are
null. Put its implementation and private helpers in that directory. Add its ID
to [`profiles/extensions.json`](../profiles/extensions.json), with
`record_double_tap` and `edit_notes` booleans. The builder compiles the selected
extensions, validates their source boundary and records their sources and
selection in package provenance. Add an `extension.json` beside the source with
three nonempty text fields: `name`, `description` and `gesture`. These provide
the browser selection row and details panel; the description should explain changes to stock
behavior and when the extension clears its state.

Native builds include the declared collection. Browser kits export those objects
as individually selectable extensions. The browser's Extensions step follows
Machines, starts with none selected, and saves choices with the machine selection.
It omits unselected extension objects entirely, and the generated registry skips
their absent accessors. The SDK's extension hooks form the profile's `extensions`
service: a build with no extension selected links none of the extension runtime
and leaves every one of its stock call sites unchanged. Only the SDK defines those
accessors and firmware hooks.

The array defines callback order. All observers receive the same immutable
event in that order. There is no priority guessing or registration during
playback. Duplicate IDs, multiple Record-double-tap owners and note editing
without that claim fail the build. An empty collection is valid.

## Events and ownership

Callbacks run synchronously on the controller path. Keep them bounded: no
allocation, blocking, I/O or logging. Borrow event references only for the
callback. The SDK does not sandbox native code.

| Callback | Meaning |
| --- | --- |
| `context` | Current project, pattern, selected track, length, scale, quantization and play state; delivered before note, tick and control events |
| `note_on` | Stock-accepted live note on the selected eligible instrument track while playing, with stock pickup position and collision radius |
| `note_off` | Selected-track live release; may arrive without a preceding accepted onset |
| `tick` | Stock-scaled Q8 duration delta; a discontinuity asks the extension to discard timing-dependent state |
| `activity` | Live input activity, including rejected notes; useful for cancelling gestures |
| `control` | Queued control after stock handling, with a 64-bit microsecond time; `record_accepted` and `unmodified_record` describe Record specifically |

Project and pattern IDs are opaque equality tokens. Lengths use pattern ticks;
scale 1 has 480 ticks per step. The adapter supplies negative pickup positions
near pattern zero. Quantization belongs to stock playback; extensions must not
invent a second grid conversion. Generated sequencer notes and step entry do
not become live onsets.

Observers cannot transform notes or suppress stock input. The only current
exclusive command is Record double-tap. Its owner recognizes the gesture; the
shared [`RecordTap`](../sdk/include/opxy/record_tap.hpp) helper handles short
taps, holds, repeats and timeouts without delaying stock controls.

Only the declared note editor can use `Actions::insert_notes`, during an
accepted Record control callback. The SDK rechecks context and validates the
bounded batch before opening one stock undo transaction. It preserves stock
collision and capacity behavior, returns the inserted prefix length and
publishes once. A successful edit permits one bounded success notification.
Calls outside that callback, from observers, after a context change, or a
second edit within the same callback are rejected.

These phases keep observation independent of pattern edits. Changing live
recording policy or transforming note-on/off pairs requires an explicit SDK
contract; an observer must not add its own firmware patch or write stock memory.

## Verify

Run `python sdk.py check`, then the full [native release verification](build.md#release-verification).
Shared tests exercise callback ordering, exclusive claims, stale-context and
unauthorized edits, plus capture through the actual adapter with stock boundary
doubles. Device scheduling still requires testing the exact built image.
