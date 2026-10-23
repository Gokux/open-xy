// Stock OS 1.2.0 track-page encoders for synths with alternate controls. Both
// hooks replace a CALL.A of a C function, so stock calls them with the C ABI.
// A press of an owned synth's encoder selects the position's next parameter; a
// turn edits the selected one. Everything else reaches stock as before.
#include "synth_controls.hpp"
#include "stock.hpp"

extern "C" {
void sdk_synth_press(opxy::u32) __asm__("sdk_synth_press");
opxy::u32 sdk_synth_turn(opxy::u32, opxy::u32, opxy::u32, opxy::u32) __asm__("sdk_synth_turn");
}

namespace {
using opxy::u32;
using opxy::u8;
using opxy::platform::SynthControls;
using namespace opxy::platform;

// Track page bank: 0 for the engine page, 1..3 for the other three pages.
u32 page_bank() { return stock<u32()>(0x8c08ff3c)(); }
// The controller on top of the GUI stack, which receives key events, and the
// track page controller's vtable.
const u32 kTrackPageVtable = 0x0803fa28;
u32 top_controller_vtable() { return *stock<const u32*()>(0x8c095008)(); }

const SynthControls* owned(u32 engine) {
    for (u32 i = 0; i < sdk_synth_control_count; ++i) {
        const SynthControls& m = sdk_synth_controls[i];
        if (m.engine == engine) return m.ready() == 1 ? &m : nullptr;
    }
    return nullptr;
}

// The slot each position shows, per track, while the track keeps an owned
// engine. Engine 0 is never a synth, so zeroed state starts on slots 0..3.
struct Track { u32 engine; u8 slots[opxy::page_controls]; };
Track tracks[kTracks];

Track* state(u32 track, u32 engine) {
    if (track >= kTracks) return nullptr;
    Track& t = tracks[track];
    if (t.engine != engine) {
        t.engine = engine;
        for (u32 i = 0; i < opxy::page_controls; ++i) t.slots[i] = static_cast<u8>(i);
    }
    return &t;
}

// The owned machine on the track and its state, or null. Any other engine
// clears the track's selection.
const SynthControls* machine(u32 track, Track*& t) {
    if (track >= kTracks) return nullptr;
    const u32 engine = track_engine(track);
    const SynthControls* m = owned(engine);
    t = state(track, m ? engine : 0);
    return m;
}

u32 shown(u32 track, u32 position) {
    Track* t;
    return position < opxy::page_controls && machine(track, t) ? t->slots[position] : position;
}
}

void sdk_synth_shown(u32 track, u8* slots) {
    for (u32 i = 0; i < opxy::page_controls; ++i) slots[i] = static_cast<u8>(shown(track, i));
}

// Reads only the selection the screen shell refreshed for this frame (no stock
// getters), so any caller of the record's name callback may use it.
u32 sdk_synth_title_slot(u32 engine, u32 index) {
    const u32 track = byte(kSelectedTrack);
    if (track >= kTracks || index >= opxy::page_controls || !engine || tracks[track].engine != engine) return index;
    return tracks[track].slots[index];
}

// 8c0b66d2: the GUI's key dispatcher records a press of encoder 0..3 (key
// codes 10..13, without shift) before passing it to the top controller, whose
// engine page does nothing with it. On the track page of an owned synth the
// press also selects the position's next parameter.
void sdk_synth_press(u32 encoder) {
    stock<void(u32)>(0x8d51e634)(encoder);
    Track* t;
    const SynthControls* m;
    if (encoder < opxy::page_controls && top_controller_vtable() == kTrackPageVtable && page_bank() == 0 &&
        (m = machine(byte(kSelectedTrack), t))) {
        const u32 next = m->next[t->slots[encoder]];
        if (next < opxy::parameter_slots) t->slots[encoder] = static_cast<u8>(next);
    }
}

// 8c090636: an encoder turn on a track page edits parameter `index` (encoder
// plus eight per page bank) of the selected track through stock, which owns
// stepping, parameter locks and publication. An owned synth's engine-page
// encoder edits the parameter its position shows.
u32 sdk_synth_turn(u32 project, u32 track, u32 index, u32 event) {
    if (index < opxy::page_controls) index = shown(track, index);
    return stock<u32(u32, u32, u32, u32)>(0x8d5ab8ec)(project, track, index, event);
}
