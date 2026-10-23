// Alternate synth controls: the collection's synths that list alternate
// parameters (one generated table, synth_control_table.cpp.in) and the GUI
// state of which parameter each page encoder edits (synth_controls.cpp).
#pragma once
#include <opxy/types.hpp>

namespace opxy { namespace platform {
// A synth whose definition lists alternates. Pressing an encoder moves its
// position from slot s to next[s]; each position starts on its own slot 0..3,
// and a slot no position reaches maps to itself. In a browser kit an
// unselected machine's ready resolves to a function returning 0.
struct SynthControls {
    u32 engine;
    int (*ready)();
    u8 next[parameter_slots];
};
}}

extern "C" {
extern const opxy::platform::SynthControls sdk_synth_controls[] __asm__("sdk_synth_controls");
extern const opxy::u32 sdk_synth_control_count __asm__("sdk_synth_control_count");
// The parameter slot each of a track's four page positions edits and shows:
// 0..3 unless an owned synth's encoder press selected an alternate. GUI only.
void sdk_synth_shown(opxy::u32 track, opxy::u8* shown) __asm__("sdk_synth_shown");
// The slot shown at page position `index` while engine is the selected track's
// owned synth, as last refreshed; other indices and engines map to themselves.
// For stock control titles.
opxy::u32 sdk_synth_title_slot(opxy::u32 engine, opxy::u32 index) __asm__("sdk_synth_title_slot");
}
