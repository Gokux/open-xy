#pragma once
#include <opxy/types.hpp>

namespace opxy {
using i16 = __INT16_TYPE__;

// Read-only view of the sample the stock allocator assigned to a voice.
// frames == 0 means no usable sample; engines then output silence.
// channels == 2 means interleaved stereo frames (layout not yet hardware-verified).
struct SampleView {
    const i16* data;
    u32 frames;
    u32 rate;
    u32 channels;
};

inline i16 sample_at(const SampleView& view, u32 frame, u32 channel = 0) {
    if (frame >= view.frames) return 0;
    return view.data[frame * view.channels + (channel < view.channels ? channel : 0)];
}
}
