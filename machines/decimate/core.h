#pragma once
#include <opxy/effect.hpp>

// Decimate: the original sample-and-hold reducer, with an optional crossover
// that selects the upper band for the send. No quantization or clock jitter.
namespace decimate {
struct State {
    opxy::i32 held_left;
    opxy::i32 held_right;
    opxy::u32 phase;
    opxy::i32 low_left;
    opxy::i32 low_right;
    opxy::i32 held_low_left;
    opxy::i32 held_low_right;
    opxy::i32 crossover;  // smoothed twice-alpha, Q15
    opxy::u32 right_offset;  // right capture phase, latched at each left capture
};
// Controls: 0 rate (hold length 1..32), 1 crossover (0 = full band;
// otherwise approximately 10000 * value^2 Hz), 2 stereo (right capture offset
// from zero to half the hold period, in whole samples),
// 3 dry (adds clean input at 0..unity gain; processed gain stays unchanged).
void initialize(State&);
void process(State&, opxy::Channel left, opxy::Channel right, opxy::Parameters parameters);
}
