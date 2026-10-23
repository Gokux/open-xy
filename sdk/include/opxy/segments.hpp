#pragma once
#include "types.hpp"

namespace opxy { namespace segments {
// Segment display: the machine declares its character count, glow layers, dials
// and text controls in definition.json (resources.display) and names the same
// frame here, e.g.
//   using Frame = opxy::segments::Frame<4>;
// The SDK owns node bindings, text setters and repainting.
// The value each control position shows and which declared parameter that is:
// its own (shown[i] == i) or an alternate selected by pressing its encoder.
struct Input {
    i32 parameters[page_controls];
    u8 shown[page_controls];
};
// A dial's rotation from its authored pose, clockwise on screen, as a Q10 unit
// vector. {0, 0} is the authored pose.
struct Dial { i32 cos, sin; };
template <u32 Characters>
struct Frame {
    static const u32 character_count = Characters;
    u32 masks[Characters];  // 14-segment glyphs, segments abcdefghjklmnp in bits 15..2
    char label[16];
    char values[page_controls][8];  // Shown in place of a declared text control's value
    u32 key;                // Nonzero; masks and label repaint only when it changes
    Dial dials[4];          // Applied every frame to the declared dials
};
inline void text(char* output, unsigned capacity, const char* input) {
    unsigned i = 0;
    for (; i + 1 < capacity && input[i]; ++i) output[i] = input[i];
    for (; i < capacity; ++i) output[i] = 0;
}
// sin of 0..90 degrees, Q10.
static const u16 sine_q10[91] = {
    0, 18, 36, 54, 71, 89, 107, 125, 143, 160, 178, 195, 213, 230, 248, 265, 282, 299, 316, 333, 350, 367, 384,
    400, 416, 433, 449, 465, 481, 496, 512, 527, 543, 558, 573, 587, 602, 616, 630, 644, 658, 672, 685, 698, 711,
    724, 737, 749, 761, 773, 784, 796, 807, 818, 828, 839, 849, 859, 868, 878, 887, 896, 904, 912, 920, 928, 935,
    943, 949, 956, 962, 968, 974, 979, 984, 989, 994, 998, 1002, 1005, 1008, 1011, 1014, 1016, 1018, 1020, 1022,
    1023, 1023, 1024, 1024};
// sin of a tenth-degree angle, Q10, interpolated between whole degrees.
inline i32 sine(i32 tenths) {
    tenths %= 3600;
    if (tenths < 0) tenths += 3600;
    const i32 sign = tenths >= 1800 ? -1 : 1;
    tenths %= 1800;
    if (tenths > 900) tenths = 1800 - tenths;
    const i32 degree = tenths / 10, fraction = tenths % 10;
    const i32 low = sine_q10[degree], high = sine_q10[degree < 90 ? degree + 1 : 90];
    return sign * (low + (high - low) * fraction / 10);
}
// A clockwise rotation by tenths of a degree.
inline Dial rotation(i32 tenths) {
    const Dial dial = {sine(tenths + 900), sine(tenths)};
    return dial;
}
// A control's Q31 value mapped onto a sweep of +/- `half` tenths of a degree
// around the authored pose, at most a full turn (1800). 32-bit arithmetic only:
// firmware links no 64-bit helpers.
inline Dial sweep(i32 value, i32 half) {
    if (value < 0) value = 0;
    if (half < 0) half = 0;
    if (half > 1800) half = 1800;
    return rotation(-half + (value >> 16) * 2 * half / 32767);
}
template <class F>
inline bool valid(const F& frame) {
    if (!frame.key || frame.label[15]) return false;
    for (unsigned i = 0; i < page_controls; ++i) if (frame.values[i][7]) return false;
    for (unsigned i = 0; i < F::character_count; ++i) if (frame.masks[i] & ~0xfffcu) return false;
    // A rotation, never a scale or skew: a unit vector within Q10 rounding.
    for (unsigned i = 0; i < 4; ++i) {
        const Dial& d = frame.dials[i];
        if (!d.cos && !d.sin) continue;
        if (d.cos < -q10_unit || d.cos > q10_unit || d.sin < -q10_unit || d.sin > q10_unit) return false;
        const i32 length = d.cos * d.cos + d.sin * d.sin;
        if (length < q10_unit * q10_unit / 16 * 15 || length > q10_unit * q10_unit / 16 * 17) return false;
    }
    return true;
}
}}
