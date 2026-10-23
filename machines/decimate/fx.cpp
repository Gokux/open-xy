#include "core.h"

namespace decimate {
namespace {
constexpr opxy::u32 kMaxHold = 32;

// Twice the TPT one-pole coefficient, Q15, at x = 0, 1/32, ... 1.
// fc = 10000*x*x; g = tan(pi*fc/44100); twice_alpha = 2*g/(1+g).
// Linear interpolation avoids trigonometry and floating point in the callback.
constexpr opxy::u32 kCrossover[] = {
    0, 46, 182, 408, 721, 1120, 1602, 2161, 2795, 3499, 4269,
    5099, 5986, 6923, 7907, 8933, 9997, 11095, 12224, 13381,
    14562, 15767, 16992, 18237, 19502, 20785, 22086, 23408,
    24750, 26114, 27504, 28922, 30371
};

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

opxy::i32 saturating_add(opxy::i32 a, opxy::i32 b) {
    if (b > 0 && a > 0x7fffffff - b) return 0x7fffffff;
    if (b < 0 && a < (-0x7fffffff - 1) - b) return -0x7fffffff - 1;
    return a + b;
}

// A complementary first-order split: high = input - low. Both state updates
// are convex blends (twice-alpha < 1), even at full-scale input.
opxy::i32 lowpass(opxy::i32 input, opxy::i32& memory, opxy::u32 twice_alpha) {
    const opxy::i32 low = blend(memory, input, twice_alpha >> 1);
    memory = blend(memory, input, twice_alpha);
    return low;
}

// held(input - low). Half-scale subtraction accommodates bipolar transients;
// saturate only if the extracted high band exceeds Q31.
opxy::i32 high_band(opxy::i32 held, opxy::i32 held_low) {
    if (held_low == 0) return held;
    const opxy::i32 half = (held >> 1) - (held_low >> 1);
    if (half > 0x3fffffff) return 0x7fffffff;
    if (half < -0x40000000) return -0x7fffffff - 1;
    return static_cast<opxy::i32>(static_cast<opxy::u32>(half) << 1);
}

opxy::i32 smooth(opxy::i32 value, opxy::i32 target) {
    const opxy::i32 difference = target - value;
    // Approximately 1.5 ms time constant; finite arrival at both endpoints.
    return value + (difference > 0 ? (difference + 63) >> 6 :
                   -((-difference + 63) >> 6));
}
}

void initialize(State& state) {
    state = State();
}

// Bounded: one pass over the 64-sample block, no allocation or stock calls.
void process(State& state, opxy::Channel left, opxy::Channel right, opxy::Parameters parameters) {
    const opxy::u32 hold = 1 + (((nonnegative(parameters[0]) >> 16) * (kMaxHold - 1) + 16384) >> 15);
    const opxy::u32 crossover = nonnegative(parameters[1]) >> 16;
    const opxy::u32 stereo = nonnegative(parameters[2]) >> 16;
    const opxy::u32 dry = nonnegative(parameters[3]) >> 16;
    const opxy::u32 index = crossover >> 10;
    const opxy::i32 target = static_cast<opxy::i32>(kCrossover[index] +
        ((kCrossover[index + 1] - kCrossover[index]) * (crossover & 1023) >> 10));
    const opxy::u32 offset = (((hold >> 1) * stereo) + 16384) >> 15;
    for (unsigned i = 0; i < opxy::block_frames; ++i) {
        state.crossover = smooth(state.crossover, target);
        opxy::i32 low_left = 0, low_right = 0;
        if (state.crossover) {
            low_left = lowpass(left[i], state.low_left, state.crossover);
            low_right = lowpass(right[i], state.low_right, state.crossover);
        } else {
            // Preserve the original full-band path, including its hold phase.
            state.low_left = state.low_right = 0;
            state.held_low_left = state.held_low_right = 0;
        }
        if (state.phase == 0) {
            // Latch once per cycle so turning Stereo cannot move this cycle's
            // capture point past the clock. Rate retains its original timing.
            state.right_offset = offset;
            state.held_left = left[i];
            state.held_low_left = low_left;
        }
        if (state.phase == state.right_offset) {
            state.held_right = right[i];
            state.held_low_right = low_right;
        }
        state.phase = state.phase + 1 >= hold ? 0 : state.phase + 1;
        // Send convention: dry is additive. Turning it up never ducks the
        // processed signal. Low Cut and Stereo never touch this clean path.
        left[i] = saturating_add(high_band(state.held_left, state.held_low_left), blend(0, left[i], dry));
        right[i] = saturating_add(high_band(state.held_right, state.held_low_right), blend(0, right[i], dry));
    }
}
}
