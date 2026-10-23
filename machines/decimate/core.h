#pragma once
#include <opxy/effect.hpp>

// Decimate: a sample-and-hold rate and bit-depth reducer. It holds, quantizes
// and crossfades samples without rescaling them, so its output keeps the send
// buffer's own scale.
namespace decimate {
struct State {
    opxy::i32 held_left;
    opxy::i32 held_right;
    opxy::u32 phase;
    opxy::u32 length;  // samples in the current hold
    opxy::u32 seed;    // jitter noise
};
// Controls: 0 rate (hold length 1..32 samples), 1 bits (1..16), 2 jitter (hold
// length varies by up to its own length), 3 mix (dry..wet).
void initialize(State&);
void process(State&, opxy::Channel left, opxy::Channel right, opxy::Parameters parameters);
}
