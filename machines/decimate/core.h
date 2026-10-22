#pragma once
#include <opxy/effect.hpp>

// Decimate: a sample-and-hold rate reducer. It holds and crossfades samples
// without rescaling them, so its output keeps the send buffer's own scale.
namespace decimate {
struct State {
    opxy::i32 held_left;
    opxy::i32 held_right;
    opxy::u32 phase;
};
// Controls: 0 rate (hold length 1..32 samples), 1 mix (dry..wet).
void initialize(State&);
void process(State&, opxy::Channel left, opxy::Channel right, opxy::Parameters parameters);
}
