#pragma once
#include <opxy/extension.hpp>

namespace opxy { namespace platform {
using extensions::RecordingContext;
using RecordedNote = extensions::Note;

// Claims and actions, one bit each, named as in profiles/extensions.json.
// A claim has one owner per build; an action needs the claim it names there.
const u32 claim_record_double_tap = 1u << 0;
const u32 action_edit_notes = 1u << 0;

struct ExtensionEntry {
    const char* id;
    u32 claims, actions;
    const extensions::Hooks* hooks;
};
const ExtensionEntry* extension_collection(u32& count);

// These entry points belong only to the version adapter.
void extensions_sync();
void extensions_input_activity();
void extensions_recordable_note_on(u32 track, u32 pitch, u32 velocity);
void extensions_selected_note_off(u32 track, u32 pitch);
void extensions_recording_tick(u32 delta);
void extensions_queued_control(u32 key, bool pressed, bool accepted, bool unmodified,
                        extensions::Time time);

RecordingContext extension_context(bool& playing);
i32 extension_position(u32 track);
u32 extension_scaled_delta(u32 track, u32 delta);
i32 extension_collision_radius(u32 track);
bool extension_record_held();
u32 extension_write(u32 track, const RecordedNote* notes, u32 count);
void extension_notify(const char* text);
}}
