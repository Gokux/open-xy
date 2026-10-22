// Stock OS 1.2.0 side of sample assignment for custom drum pages: the header
// worker's frame-count hook, the region initializer hook and the ownership
// test the retry stubs use. Stock calls the two hooks with the ordinary C ABI
// (each replaces a CALL to the function it forwards to); the retry stubs and
// the owned initializer call stay in sample_assignment.s.
#include "sample_region.hpp"

extern "C" {
opxy::u32 extensions_sample_controls_kind(opxy::u32) __asm__("extensions_sample_controls_kind");
opxy::u32 extensions_sample_key(opxy::u32, opxy::u32) __asm__("extensions_sample_key");
opxy::u32 sdk_sample_assignment(opxy::u32, opxy::u32, opxy::u32, const opxy::u32*, opxy::u32)
    __asm__("sdk_sample_assignment");
void sdk_sample_cache_barrier() __asm__("sdk_sample_cache_barrier");
opxy::u32 sdk_sample_assign_owned(opxy::u32, opxy::u32, opxy::u32, opxy::u32, opxy::u32, opxy::u32)
    __asm__("sdk_sample_assign_owned");
opxy::u32 sdk_sample_assignment_frames(opxy::u32) __asm__("sdk_sample_assignment_frames");
opxy::u32 sdk_sample_assign_region(opxy::u32, opxy::u32, opxy::u32, opxy::u32, opxy::u32, opxy::u32, opxy::u32)
    __asm__("sdk_sample_assign_region");
opxy::u32 sdk_sample_retry_owned(opxy::u32) __asm__("sdk_sample_retry_owned");
}

namespace {
using opxy::u32;
template <class Function> Function* stock(u32 address) { return reinterpret_cast<Function*>(address); }
u32 word(u32 address) { return *reinterpret_cast<const volatile u32*>(address); }
const u32 kJob = 0x0801f7f8;                // header worker job: +0 raw key, +4 track, +12 generation
const u32 kActiveGeneration = 0x0801f804;
const u32 kPendingGeneration = 0x0801f6a0;
const u32 kActivePath = 0x0801f7dc;         // the worker's own path, never the browser's pending choice
const u32 kWorkerBusy = 0x0801f7bc;         // byte
const u32 kSelectedTrack = 0x8409d2d8;      // byte
u32 engine(u32 track) { return stock<u32(u32)>(0x8d585eb4)(track); }
bool owned(u32 track) { return track < 8 && extensions_sample_controls_kind(engine(track)) != 0; }

// The header worker's metadata for the job it just read, consumed once by the
// region initializer of the same job. valid is published last. Pad settings
// are read at commit time so edits made during loading are not lost.
struct Hint { u32 valid, rate, track, key, generation, frames; };
volatile Hint hint;
}

// 8c0a2cee: the header worker holds this reader until its completion is
// queued. Keep stock's full frame count; the rate is another constant-time getter.
u32 sdk_sample_assignment_frames(u32 reader) {
    const u32 frames = stock<u32(u32)>(0x8d4fd146)(reader);
    hint.valid = 0;
    sdk_sample_cache_barrier();
    const u32 track = word(kJob + 4), key = word(kJob), generation = word(kJob + 12);
    if (!owned(track)) return frames;
    hint.rate = stock<u32(u32)>(0x8d4fd12c)(reader);
    hint.track = track;
    hint.key = key;
    hint.generation = generation;
    hint.frames = frames;
    sdk_sample_cache_barrier();
    hint.valid = 1;
    return frames;
}

// 8c0a2de4: stock 8d588224(track, key, ...) initializes a new region. For an
// owned drum page, let the machine combine saved settings with metadata from
// this exact job. Stock has replaced the path but not yet reset pad metadata.
u32 sdk_sample_assign_region(u32 track, u32 key, u32 third, u32 fourth, u32 fifth, u32 frames, u32 last) {
    if (!owned(track))
        return stock<u32(u32, u32, u32, u32, u32, u32, u32)>(0x8d588224)(track, key, third, fourth, fifth, frames, last);
    u32 scratch;
    void* raw = stock<void*(u32, u32, u32*, u32)>(0x8d587904)(track, key, &scratch, 0);
    const opxy::platform::SampleReplacement previous = opxy::platform::sample_replacement(raw);
    u32 rate = 44100;
    const u32* path = nullptr;
    if (hint.valid == 1) {
        sdk_sample_cache_barrier();
        hint.valid = 0;
        if (hint.track == track && hint.key == key && hint.frames == frames &&
            word(kActiveGeneration) == hint.generation && word(kPendingGeneration) == hint.generation) {
            rate = hint.rate;
            path = reinterpret_cast<const u32*>(kActivePath);
        }
    }
    const u32 settings = sdk_sample_assignment(track, frames, rate, path, previous.settings);
    // Stock normalizes its lookup key but stores the input key. Keep the raw
    // note for lookup; the owned fade hook supplies the canonical stored key.
    // Passing the canonical key into stock would apply the octave twice.
    const u32 result = sdk_sample_assign_owned(track, key, settings, frames, last, extensions_sample_key(track, key));
    // No publisher runs inside the stock initializer. Restore saved controls
    // before returning to its caller's sort and subsequent GUI publication.
    opxy::platform::sample_restore_replacement(raw, previous);
    return result;
}

// Retry stubs: whether an owned drum page on the selected track may retry.
// Active: the active and pending generations differ. Pending: the worker is idle.
u32 sdk_sample_retry_owned(u32 pending) {
    if (pending ? *reinterpret_cast<const volatile unsigned char*>(kWorkerBusy) != 0
                : word(kActiveGeneration) == word(kPendingGeneration)) return 0;
    return owned(*reinterpret_cast<const volatile unsigned char*>(kSelectedTrack));
}
