#include <opxy/extension.hpp>
#include <opxy/record_tap.hpp>
#include "history.hpp"

namespace opxy { namespace extensions { namespace capture {
namespace {
RecordingHistory history;
RecordTap tap;
Context previous;
Note snapshot[RecordingHistory::capacity];
u32 snapshot_count;

void context(const Context& context) {
    if (!(context.recording == previous.recording) || context.playing != previous.playing) tap.cancel();
    history.sync(context.recording, context.playing);
    previous = context;
}
void input_activity() { tap.cancel(); }
void recordable_note_on(const Context&, const LiveNote& note) {
    history.note_on(note.position, note.pitch, note.velocity, note.collision_radius);
}
void selected_note_off(const Context&, const NoteOff& note) { history.note_off(note.pitch); }
void recording_tick(const Context&, const Tick& tick) {
    if (tick.discontinuity) { history.clear(); tap.cancel(); return; }
    history.advance(tick.delta_q8);
}
void queued_control(const Context& context, const Control& control, const Actions& actions) {
    if (control.key != Control::record_key) { tap.cancel(); return; }
    if (!control.record_accepted || !context.recording.eligible) {
        // Still end the tap, or the next press would read as a key repeat.
        if (!control.pressed) tap.release(control.time);
        tap.cancel(); return;
    }
    if (control.pressed) {
        if (tap.press(control.time, control.unmodified_record))
            snapshot_count = history.snapshot(snapshot, RecordingHistory::capacity);
        return;
    }
    if (!tap.release(control.time) || !snapshot_count) return;
    const u32 written = actions.insert_notes(context, snapshot, snapshot_count);
    // Keep the take unless all of it fit; the written notes stay, with Undo.
    if (written == snapshot_count) {
        history.clear();
        actions.notify("captured");
    } else if (written) {
        actions.notify("pattern full");
    }
}
}
// In Hooks order; null for an event this extension does not take.
extern const Hooks hooks = {context, recordable_note_on, selected_note_off, recording_tick,
                            input_activity, queued_control};
}}}
