#pragma once
#include <opxy/types.hpp>

namespace opxy { namespace extensions {

// Opaque project/pattern identities are only for equality, never dereferencing.
// Positions and lengths use stock pattern ticks (480 per step at scale 1).
struct RecordingContext {
    u32 project, pattern, track, length, scale, quantization;
    bool eligible;
    bool operator==(const RecordingContext& other) const {
        return project == other.project && pattern == other.pattern &&
            track == other.track && length == other.length && scale == other.scale &&
            quantization == other.quantization && eligible == other.eligible;
    }
};
struct Context { RecordingContext recording; bool playing; };
struct Note { i32 position; u32 length; u8 pitch, velocity; };
struct LiveNote { u32 track, pitch, velocity; i32 position; u32 collision_radius; };
struct NoteOff { u32 track, pitch; };
struct Tick { u32 delta_q8; bool discontinuity; };
using Time = __UINT64_TYPE__;
struct Control {
    static const u32 record_key = 50;
    u32 key;
    bool pressed, record_accepted, unmodified_record;
    Time time;
};

// Callable only during an authorized control callback. The SDK validates the
// context again and owns undo/publication: one stock undo transaction per
// callback. Returns the inserted prefix length. A notification is allowed only
// after this callback successfully edits notes. Append new actions at the end.
struct Actions {
    // Add notes to the selected track's pattern beside its existing notes.
    u32 (*insert_notes)(const Context&, const Note*, u32 count);
    void (*notify)(const char* text);
    // Replace the selected track's pattern notes with these. Refused, changing
    // nothing, while stock is still recording a held note.
    u32 (*replace_notes)(const Context&, const Note*, u32 count);
};

// One callback per event, named for what it delivers. Each event lists its
// firmware sites in the profile ("events"); docs/extensions.md says how to
// widen one or propose another. Append new callbacks at the end only: an
// extension initializes this aggregate by position.
//
// All callbacks are synchronous on the controller path, in collection order.
// Arguments are borrowed for the callback. No allocation, blocking or I/O.
// Observers cannot transform live input or consume stock controls.
struct Hooks {
    // Selected-track recording context and play state; before every other event.
    void (*context)(const Context&);
    // A live onset stock accepted for recording, on the selected eligible
    // instrument track, while playing. Sequenced notes and step entry excluded.
    void (*recordable_note_on)(const Context&, const LiveNote&);
    // A live release on the selected track, playing or not; it may have no
    // preceding recordable onset.
    void (*selected_note_off)(const Context&, const NoteOff&);
    // The selected track's scaled recording time, while playing and eligible.
    void (*recording_tick)(const Context&, const Tick&);
    // Any live note input, accepted or not, on any track.
    void (*input_activity)();
    // A queued control (Record and other queued keys; not keyboard keys
    // 26-49) after stock handled it. Actions act only for their claim owner.
    void (*queued_control)(const Context&, const Control&, const Actions&);
};
}}
