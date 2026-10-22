#pragma once
#include <opxy/types.hpp>

namespace opxy {
// Decode the stock audio clock's positive IEEE-754 binary32 BPM without using
// floating-point helpers. Outside 20..300 BPM, return the Transport invalid value.
// The bounded exponent gives shifts 15..19; mantissa*10 and rounding fit u32.
inline u32 audio_bpm_x10(u32 bits) {
    if (bits < 0x41a00000u || bits > 0x43960000u) return 0;
    const u32 exponent = bits >> 23;
    const u32 mantissa = (bits & 0x007fffffu) | 0x00800000u;
    const u32 shift = 150u - exponent;
    return (mantissa * 10u + (1u << (shift - 1u))) >> shift;
}
}
