#pragma once
#include <opxy/types.hpp>

namespace opxy {
// Advisory tempo and transport state, read by the SDK once per block.
// bpm_x10 == 0 means no valid tempo; ticks advance 96 per quarter note and
// only while playing.
struct Transport {
    u32 bpm_x10;
    u32 ticks96;
    bool playing;
};
}
