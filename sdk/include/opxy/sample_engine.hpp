#pragma once
#include <opxy/audio.hpp>
#include <opxy/sample.hpp>
#include <opxy/sample_analysis.hpp>
#include <opxy/transport.hpp>

namespace opxy {
// A snapshot of the current audio voice, never the GUI-selected pad.
// The SDK clamps half-open bounds to the borrowed sample. An empty interval
// means silence. Level is unsigned Q27, unity = 0x08000000.
struct SampleRegion {
    u32 begin;
    u32 end;
    u32 level;
    bool reverse;
    i32 root_cents;
    u32 fade_q31;
};

// Per-pad extension storage. The platform serializes 16 bits exactly, including
// stock's float conversion on project save. Uninitialized regions retain their
// stock tuning/fade metadata so a machine can migrate an earlier saved format.
struct SampleSettings { u32 value; bool initialized; };
struct SampleControl { u32 knob; i32 direction; bool pressed; bool shifted; };
struct SampleAssignment {
    const char* filename;
    u32 filename_bytes;
    u32 frames;
    u32 rate;
    Transport transport;
    // Settings of the pad being replaced, when it held an assigned sample.
    // The machine decides which values survive the new sample's metadata.
    SampleSettings previous;
};
// The stock drum page supplies pitch/play/trim graphics and reverse/volume
// glyphs. Given the saved settings and eight live Q31 parameters, a machine
// supplies a live pitch offset, effective play mode and two short Shift
// captions. The SDK adds the stock region's saved pad pitch for painting.
struct SamplePanel {
    i32 pitch_cents;
    u32 repeat; // 0 = play once, 1 = loop
    char shifted[2][16];
};

// All pointers are borrowed for this call. Analysis is immutable and can be
// absent while preparation is pending, unsupported or out of cache budget.
// It belongs to the same retained PCM as the voice, through its destruction.
struct SampleBlock {
    Output output;
    Parameters parameters;
    Pitch pitch;
    Transport transport;
    SampleRegion region;
    const SampleAnalysis* analysis;
    SampleSettings settings;
    // 1: 64 mono words; 2: 64 interleaved L/R frames (128 words).
    // Zero from an older aggregate initializer retains the mono contract.
    u32 output_channels;
    // Track settings transpose in semitones (-36..36), independent of the
    // pad key, saved region tuning and live parameter-zero pitch offset.
    i32 track_transpose;
    // Drum note's octave displacement from its canonical pad, in semitones.
    // Captured at note start; changing keyboard octave does not retune a voice.
    i32 key_transpose;
};
}
