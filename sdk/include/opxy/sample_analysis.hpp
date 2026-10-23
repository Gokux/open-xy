#pragma once
#include <opxy/sample.hpp>

namespace opxy {
// Data a sample machine derives from its retained sample outside the audio
// callback, for machines declaring "sampleAnalysis". The SDK runs preparation
// in bounded chunks on the stock file worker, owns the storage and its memory
// budget, and hands the machine's voices the completed, immutable result. The
// meaning of `words` and `info` belongs to the machine.
struct SampleAnalysis {
    SampleView sample;  // the retained PCM this was prepared from
    const u32* words;
    u32 word_count;
    u32 info;
};
enum PrepareStatus : u32 { prepare_failed = 0, prepare_done = 1, prepare_running = 2 };
// A machine declaring sampleAnalysis implements, in its namespace:
//   struct Preparation;  // job state, value-initialized before each sample
//   u32 analysis_words(const SampleView&);  // storage the sample needs; 0 declines it
//   bool prepare_begin(Preparation&, const SampleView&, u32* storage, u32 words);
//   PrepareStatus prepare_step(Preparation&, u32 frames, u32& cursor);
//       processes at most `frames` source frames; cursor reports progress.
//   bool prepared(const Preparation&, SampleAnalysis&);  // words is the storage
}
