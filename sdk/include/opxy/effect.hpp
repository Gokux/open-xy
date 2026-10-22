#pragma once
#include "audio.hpp"

namespace opxy {
// Send effects process one 64-frame stereo block in place:
//   struct State { ... };
//   void initialize(State& state);
//   void process(State& state, opxy::Channel left, opxy::Channel right,
//                opxy::Parameters parameters);
// Stock constructs the effect inside a 480-byte slot behind a one-word object
// header and never destroys it, so State holds no resources.
using Channel = i32* __restrict;
const unsigned effect_state_bytes = 476;
const unsigned effect_state_alignment = 4;
}
