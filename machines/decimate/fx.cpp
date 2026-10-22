#include "core.h"

namespace decimate {
namespace {
constexpr opxy::u32 kMaxHold = 32;

opxy::u32 nonnegative(opxy::i32 value) { return value < 0 ? 0u : static_cast<opxy::u32>(value); }

// Linear crossfade with a Q15 weight (0..32767); exact dry at 0 and wet at full scale.
// 32-bit only: the halved difference is split into 15-bit halves so neither product overflows.
opxy::i32 blend(opxy::i32 dry, opxy::i32 wet, opxy::u32 weight) {
    if (weight >= 32767) return wet;
    const opxy::i32 half = (wet >> 1) - (dry >> 1);                    // |half| < 2^31
    const opxy::i32 high = (half >> 15) * static_cast<opxy::i32>(weight);  // < 2^16 * 2^15
    const opxy::i32 low = static_cast<opxy::i32>((static_cast<opxy::u32>(half) & 0x7fff) * weight >> 15);
    // The result lies between dry and wet; unsigned wraparound keeps the
    // intermediate (which can exceed 31 bits) defined.
    return static_cast<opxy::i32>(static_cast<opxy::u32>(dry) + (static_cast<opxy::u32>(high + low) << 1));
}
}

void initialize(State& state) {
    state = State();
}

// Bounded: one pass over the 64-sample block, no calls, no allocation.
void process(State& state, opxy::Channel left, opxy::Channel right, opxy::Parameters parameters) {
    const opxy::u32 hold = 1 + (((nonnegative(parameters[0]) >> 16) * (kMaxHold - 1) + 16384) >> 15);
    const opxy::u32 mix = nonnegative(parameters[1]) >> 16;
    for (unsigned i = 0; i < opxy::block_frames; ++i) {
        if (state.phase == 0) {
            state.held_left = left[i];
            state.held_right = right[i];
        }
        state.phase = state.phase + 1 >= hold ? 0 : state.phase + 1;
        left[i] = blend(left[i], state.held_left, mix);
        right[i] = blend(right[i], state.held_right, mix);
    }
}
}
