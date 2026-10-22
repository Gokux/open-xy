// SDK preview transport for the segment display. Never linked into firmware.
#include "segment_binding.cpp"
namespace {
opxy::segments::Input input;
opxy::binding::SegmentFrame frame;
}
extern "C" {
opxy::u32 opxy_segment_input_bytes() { return sizeof(input); }
opxy::u32 opxy_segment_frame_bytes() { return sizeof(frame); }
opxy::u32 opxy_segment_characters() { return opxy::binding::SegmentFrame::character_count; }
opxy::segments::Input* opxy_segment_input() { return &input; }
opxy::binding::SegmentFrame* opxy_segment_frame() { return &frame; }
opxy::u32 opxy_segment_render() { return opxy::binding::segment_render(&input, &frame); }
}
