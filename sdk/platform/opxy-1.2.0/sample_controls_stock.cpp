// Stock OS 1.2.0 drum-page encoder bridge. Each hook replaces a CALL to the
// function it forwards to, so stock calls it with the ordinary C ABI. Machine
// policy is in the generated sample callbacks.
#include <opxy/types.hpp>

extern "C" {
opxy::u32 extensions_sample_controls_kind(opxy::u32) __asm__("extensions_sample_controls_kind");
opxy::u32 extensions_sample_alias(opxy::u32) __asm__("extensions_sample_alias");
opxy::u32 sdk_sample_edit(void*, opxy::u32, opxy::i32, opxy::u32) __asm__("sdk_sample_edit");
opxy::u32 sdk_sample_ui_engine(opxy::u32) __asm__("sdk_sample_ui_engine");
opxy::u32 sdk_sample_press_engine_owned(opxy::u32, opxy::u32) __asm__("sdk_sample_press_engine_owned");
opxy::u32 sdk_sample_region_control(opxy::u32, opxy::u32, const opxy::u32*, opxy::u32) __asm__("sdk_sample_region_control");
opxy::u32 sdk_sample_selected_engine() __asm__("sdk_sample_selected_engine");
opxy::u32 sdk_sample_live_pitch_kind(opxy::u32) __asm__("sdk_sample_live_pitch_kind");
opxy::u32 sdk_sample_octave_store(opxy::u32, opxy::i32) __asm__("sdk_sample_octave_store");
extern volatile opxy::i32 sdk_sample_drum_octaves[8] __asm__("sdk_sample_drum_octaves");
void sdk_sample_cache_barrier() __asm__("sdk_sample_cache_barrier");
}

namespace {
using opxy::i32;
using opxy::u32;
template <class Function> Function* stock(u32 address) { return reinterpret_cast<Function*>(address); }
const u32 kSelectedTrack = 0x8409d2d8;  // byte
u32 engine(u32 track) { return stock<u32(u32)>(0x8d585eb4)(track); }
bool shift_held() { return stock<u32()>(0x8d51e5bc)() != 0; }
// The stored region for a track's pad, or null.
void* region_of(u32 track, u32 key) {
    u32 scratch;
    return stock<void*(u32, u32, u32*, u32)>(0x8d587904)(track, key, &scratch, 0);
}
// Stock region control: mutation for its own controls, then publication.
u32 region_control(u32 key, u32 control, const u32* event, u32 fine) {
    return stock<u32(u32, u32, const u32*, u32)>(0x8d4dcab8)(key, control, event, fine);
}
// Publish through pitch with a zero delta: keeps stored tuning and machine
// settings. Stock's fade handler would quantize even a zero delta.
u32 publish(u32 key) {
    const u32 zero[3] = {0, 0, 0};
    return region_control(key, 5, zero, 0);
}
}

// 8c0b1e76: the page asks which engine the track uses.
u32 sdk_sample_ui_engine(u32 track) { return extensions_sample_alias(engine(track)); }

// 8d58d9ca: after stock clamps the octave, mirror its stored value immediately.
// SDK IDs use stock's single-octave keyboard spacing. No engine/project getter:
// this setter also runs while loading a project or preset. A sample lookup may
// be cached, so it cannot be the only place that publishes octave changes.
u32 sdk_sample_octave_store(u32 track, i32 octave) {
    const u32 result = stock<u32(u32, i32)>(0x8d583cc4)(track, octave);
    if (track < 8) {
        sdk_sample_drum_octaves[track] = octave;
        sdk_sample_cache_barrier();
    }
    return result;
}

// 8d5ab6da: only the live/step parameter editor's pitch classification.
// Stock checks parameter zero after this call and performs its own cents
// stepping and lock publication. Keep the real engine ID and all other
// parameter paths unchanged; a conflicting/unowned registration stays stock.
u32 sdk_sample_live_pitch_kind(u32 id) {
    if (extensions_sample_controls_kind(id) == 7) return 1;
    return stock<u32(u32)>(0x8d5b5b68)(id);
}

// 8c0b3290 (through the stub in sample_controls.s): an encoder press. button
// is the index minus six (4..7). Main first/fourth and Shift second/third go
// to the machine; owned presses never enter stock's mode cycle.
u32 sdk_sample_press_engine_owned(u32 track, u32 button) {
    if (track >= 8) return 33;
    const u32 id = engine(track);
    if (!extensions_sample_controls_kind(id)) return extensions_sample_alias(id);
    const bool shifted = shift_held();
    const bool routed = shifted ? button == 5 || button == 6 : button == 4 || button == 7;
    if (routed && track < 8) {
        const u32 key = stock<u32(u32)>(0x8d4d7650)(track);
        if (void* region = region_of(track, key)) {
            if (sdk_sample_edit(region, button + (shifted ? 8 : 4), 0, id)) publish(key);
        }
    }
    return id;
}

// 8c0b21c6: an encoder turn. Stock keeps trim, reverse and volume mutation
// and all publication; the machine receives its own controls.
u32 sdk_sample_region_control(u32 key, u32 control, const u32* event, u32 fine) {
    const u32 track = *reinterpret_cast<const volatile unsigned char*>(kSelectedTrack);
    const u32 id = track < 8 ? engine(track) : 33;
    if ((control <= 3 || control == 5 || control == 6) && extensions_sample_controls_kind(id)) {
        // Middle encoders edit the outer markers through stock's normalizer.
        if (control == 1) return region_control(key, 0, event, fine);
        if (control == 2) return region_control(key, 3, event, fine);
        void* region = region_of(track, key);
        if (!region || !event[1]) return static_cast<u32>(reinterpret_cast<__UINTPTR_TYPE__>(region));
        // Keep the engine paired with the active track used for this region.
        // The renderer's cached sample-page track can lag track navigation.
        if (sdk_sample_edit(region, control, static_cast<i32>(event[1]), id)) return publish(key);
        return 0;
    }
    return region_control(key, control, event, fine);
}

u32 sdk_sample_selected_engine() { return engine(stock<u32()>(0x8d4d78cc)()); }
