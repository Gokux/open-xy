// Stock OS 1.2.0 side of the analysis progress overlay: the GUI frame hook
// and the stock popup it shares with other notifications. GUI role only; no
// audio caller enters these. Device-only: the host fixture supplies doubles.
#include <opxy/types.hpp>

extern "C" {
opxy::u32 extensions_sample_analysis_ready() __asm__("extensions_sample_analysis_ready");
opxy::u32 extensions_sample_analysis_kind(opxy::u32) __asm__("extensions_sample_analysis_kind");
void sdk_sample_gui_tick() __asm__("sdk_sample_gui_tick");
opxy::u32 sdk_sample_progress_frame(opxy::u32) __asm__("sdk_sample_progress_frame");
int sdk_sample_progress_context() __asm__("sdk_sample_progress_context");
int sdk_sample_popup_active() __asm__("sdk_sample_popup_active");
int sdk_sample_popup_matches(const char*, unsigned) __asm__("sdk_sample_popup_matches");
void sdk_sample_popup_publish(const char*, unsigned) __asm__("sdk_sample_popup_publish");
}

namespace {
using opxy::u32;
template <class Function> Function* stock(u32 address) { return reinterpret_cast<Function*>(address); }
u32 word(u32 address) { return *reinterpret_cast<const volatile u32*>(address); }
const volatile unsigned char* bytes(u32 address) { return reinterpret_cast<const volatile unsigned char*>(address); }
const u32 kScreen = 0x84008c64;         // current GUI screen; 4 is the sample browser
const u32 kSelectedTrack = 0x8409d2d8;  // byte
const u32 kPopupState = 0x84054538;     // bytes: shown, persistent
const u32 kPopupText = 0x84ebea18;      // stock string: +4 inline data or pointer, +20 size, +24 capacity
}

// 8d51de40: once per GUI frame, before stock draws it.
u32 sdk_sample_progress_frame(u32 frame) {
    sdk_sample_gui_tick();
    return stock<u32(u32)>(0x8d52082c)(frame);
}
// Only an analysis machine on the selected track, outside the sample browser, may notify.
int sdk_sample_progress_context() {
    if (extensions_sample_analysis_ready() != 1 || word(kScreen) == 4) return 0;
    const u32 track = *bytes(kSelectedTrack);
    if (track >= 8) return 0;
    return extensions_sample_analysis_kind(stock<u32(u32)>(0x8d585eb4)(track)) != 0;
}
int sdk_sample_popup_active() { return stock<int()>(0x8d5486c8)(); }
// A shared popup is ours only while it shows exactly our last text, transiently.
int sdk_sample_popup_matches(const char* text, unsigned length) {
    const volatile unsigned char* state = bytes(kPopupState);
    if (state[0] != 1 || state[1] != 0) return 0;
    const u32 capacity = word(kPopupText + 24);
    if (word(kPopupText + 20) != length || capacity < length) return 0;
    const volatile unsigned char* current =
        capacity < 16 ? bytes(kPopupText + 4) : reinterpret_cast<const volatile unsigned char*>(word(kPopupText + 4));
    if (!current) return 0;
    for (unsigned i = 0; i <= length; ++i)
        if (current[i] != static_cast<unsigned char>(text[i])) return 0;
    return 1;
}
// Stock takes the duration as binary32 bits in its fourth argument; no floating point here.
void sdk_sample_popup_publish(const char* text, unsigned seconds_bits) {
    stock<void(const char*, u32, u32, u32)>(0x8d548580)(text, 1, 0, seconds_bits);
}
