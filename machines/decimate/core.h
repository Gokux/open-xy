#pragma once
#include <opxy/types.hpp>

// Decimate: a sample-and-hold rate reducer used as the first send-effect probe.
// It never rescales samples, so it behaves the same whatever the stock buffer
// scale turns out to be.
namespace decimate {
struct State {
    opxy::i32 held_left;
    opxy::i32 held_right;
    opxy::u32 phase;
    opxy::u32 slot;
};
// Parameters are the stock eight-word vector; negative values clamp to zero.
// 0: rate (hold length 1..32 samples), 1: mix (dry..wet).
void init(State&, opxy::u32 slot);
void process(State&, opxy::i32* left, opxy::i32* right, const opxy::i32* parameters);
}
