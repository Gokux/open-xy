#include "extension_runtime.hpp"

namespace opxy { namespace platform {
namespace {
extensions::Context current;
const ExtensionEntry* entries;
u32 entry_count;
bool initialized, dispatching, can_edit, edited, attempted;
char notification[32];

bool same_text(const char* a, const char* b) {
    if (!a || !b) return false;
    while (*a && *a == *b) { ++a; ++b; }
    return *a == *b;
}
bool ready() {
    if (initialized) return entries != nullptr;
    initialized = true;
    u32 count = 0;
    const ExtensionEntry* list = extension_collection(count);
    if (!list || count > 16) return false;
    u32 claimed = 0;
    for (u32 i = 0; i < count; ++i) {
        const ExtensionEntry& entry = list[i];
        if (!entry.id || !*entry.id || !entry.hooks || (entry.claims & claimed) ||
            ((entry.actions & action_edit_notes) && !(entry.claims & claim_record_double_tap)) ||
            ((entry.claims & claim_record_double_tap) && !entry.hooks->queued_control)) return false;
        claimed |= entry.claims;
        for (u32 j = 0; j < i; ++j)
            if (same_text(entry.id, list[j].id)) return false;
    }
    entries = list;
    entry_count = count;
    return true;
}

u32 write_notes(const extensions::Context& expected, const RecordedNote* notes, u32 count, bool replace) {
    if (!can_edit || attempted || !notes || !count || count > 120) return 0;
    bool playing = false;
    const RecordingContext now = extension_context(playing);
    if (!now.eligible || now.track >= 8 || !now.length || now.length >= (1u << 23) ||
        !(now == expected.recording) || playing != expected.playing ||
        !(now == current.recording) || playing != current.playing) return 0;
    for (u32 i = 0; i < count; ++i)
        if (notes[i].pitch > 127 || !notes[i].velocity || notes[i].velocity > 127 ||
            notes[i].position < -240 || notes[i].position >= static_cast<i32>(now.length) ||
            notes[i].length > now.length) return 0;
    attempted = true; // One undo transaction per callback, including failures.
    const u32 written = extension_write(now.track, notes, count, replace);
    edited = written != 0;
    return written;
}
void notify(const char* text) {
    if (!can_edit || !edited || !text) return;
    u32 length = 0;
    while (length < 32 && text[length]) ++length;
    if (!length || length == 32) return;
    for (u32 i = 0; i <= length; ++i) notification[i] = text[i];
    extension_notify(notification);
    edited = false; // At most one success notification per transaction.
}
u32 insert_notes(const extensions::Context& expected, const RecordedNote* notes, u32 count) {
    return write_notes(expected, notes, count, false);
}
u32 replace_notes(const extensions::Context& expected, const RecordedNote* notes, u32 count) {
    return write_notes(expected, notes, count, true);
}
const extensions::Actions actions = {insert_notes, notify, replace_notes};
}

void extensions_sync() {
    if (dispatching || !ready()) return;
    current.recording = extension_context(current.playing);
    dispatching = true;
    for (u32 i = 0; i < entry_count; ++i)
        if (entries[i].hooks->context) entries[i].hooks->context(current);
    dispatching = false;
}
void extensions_input_activity() {
    if (dispatching || !ready()) return;
    dispatching = true;
    for (u32 i = 0; i < entry_count; ++i)
        if (entries[i].hooks->input_activity) entries[i].hooks->input_activity();
    dispatching = false;
}
void extensions_recordable_note_on(u32 track, u32 pitch, u32 velocity) {
    if (dispatching) return;
    extensions_sync();
    if (!entries || track != current.recording.track || !current.recording.eligible ||
        !current.playing || pitch > 127 || velocity > 127) return;
    const i32 radius = extension_collision_radius(track);
    if (radius < 0) return;
    const extensions::LiveNote note = {track, pitch, velocity, extension_position(track),
                                       static_cast<u32>(radius)};
    dispatching = true;
    for (u32 i = 0; i < entry_count; ++i)
        if (entries[i].hooks->recordable_note_on) entries[i].hooks->recordable_note_on(current, note);
    dispatching = false;
}
void extensions_selected_note_off(u32 track, u32 pitch) {
    if (dispatching) return;
    extensions_sync();
    extensions_input_activity();
    if (!entries || track != current.recording.track) return;
    const extensions::NoteOff note = {track, pitch};
    dispatching = true;
    for (u32 i = 0; i < entry_count; ++i)
        if (entries[i].hooks->selected_note_off) entries[i].hooks->selected_note_off(current, note);
    dispatching = false;
}
void extensions_recording_tick(u32 delta) {
    if (dispatching) return;
    extensions_sync();
    if (!entries || !current.recording.eligible || !current.playing) return;
    const bool discontinuity = delta > 0x007fffffu;
    const extensions::Tick tick = {discontinuity ? 0 : extension_scaled_delta(current.recording.track, delta),
                                   discontinuity};
    dispatching = true;
    for (u32 i = 0; i < entry_count; ++i)
        if (entries[i].hooks->recording_tick) entries[i].hooks->recording_tick(current, tick);
    dispatching = false;
}
void extensions_queued_control(u32 key, bool pressed, bool accepted, bool unmodified, extensions::Time time) {
    if (dispatching) return;
    extensions_sync();
    if (!entries) return;
    const extensions::Control control = {key, pressed, accepted, unmodified, time};
    dispatching = true;
    for (u32 i = 0; i < entry_count; ++i) {
        can_edit = (entries[i].actions & action_edit_notes) && (entries[i].claims & claim_record_double_tap) &&
            key == extensions::Control::record_key && accepted;
        edited = attempted = false;
        if (entries[i].hooks->queued_control) entries[i].hooks->queued_control(current, control, actions);
        can_edit = edited = attempted = false;
    }
    dispatching = false;
}
}}
