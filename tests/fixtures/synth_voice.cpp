// SDK ABI fixture: drive the generated synth voice adapter as stock does, with
// a machine of two voices and every stock voice index 0..255. Stock renders each
// sounding index once per block, asks for an index's object before each note
// there, and ends a note by no longer rendering it.
#include "voice.cpp"
#include <cstring>
#include <initializer_list>

int destroyed[257];
// Every encoder shows an alternate. Record names must still identify raw slots.
opxy::u32 sdk_synth_title_slot(opxy::u32, opxy::u32 index) { return index + 4; }

namespace {
typedef int (*Method)(void*);
typedef int (*Render)(void*, opxy::i32*, const opxy::i32*);
void* handle[256];
int call(unsigned index, unsigned entry) {
    const void* const* table = *static_cast<const void* const* const*>(handle[index]);
    return reinterpret_cast<Method>(const_cast<void*>(table[entry]))(handle[index]);
}
// The owner a voice index renders as, 0 for silence; -1 when output is mixed.
opxy::i32 rendered(unsigned index) {
    const void* const* table = *static_cast<const void* const* const*>(handle[index]);
    opxy::i32 output[64], parameters[8] = {};
    for (opxy::i32& word : output) word = -7;
    reinterpret_cast<Render>(const_cast<void*>(table[2]))(handle[index], output, parameters);
    for (opxy::i32 word : output)
        if (word != output[0]) return -1;
    return output[0] >> 16;
}
// One stock block: each listed index renders once, as the given owner (0: silence).
struct Expect { unsigned index; opxy::i32 owner; };
bool block(std::initializer_list<Expect> expected) {
    bool ok = true;
    for (const Expect& e : expected) ok = rendered(e.index) == e.owner && ok;
    return ok;
}
// A note as stock starts it: a fresh object for the index, then start.
void note(unsigned index) {
    handle[index] = probe_factory(index);
    call(index, 4);
}
unsigned initialized() {
    unsigned total = 0;
    for (const Slot& slot : voices) total += slot.voice.initialized;
    return total;
}
}

int main() {
    const char* labels[] = {"shape", "width", "level", "motion", "extra 0", "extra 1", "extra 2", "extra 3"};
    for (unsigned i = 0; i < 8; ++i)
        if (std::strcmp(probe_parameter_name(i), labels[i])) return 11;
    if (*probe_parameter_name(8) || *probe_parameter_name(0xffffffffu)) return 12;
    // Every stock index gets an object; none past the last.
    for (unsigned i = 0; i < 256; ++i)
        if (!(handle[i] = probe_factory(i))) return 1;
    if (probe_factory(256)) return 2;
    // Nothing sounds before a note.
    if (!block({{200, 0}})) return 3;
    // Two notes take the two voices; a third, while both sound, the spare.
    note(0); note(1);
    if (!block({{0, 1}, {1, 2}})) return 4;
    note(200);
    if (destroyed[1] || !block({{0, 1}, {1, 2}, {200, 201}})) return 5;
    // A fourth note while all sound takes the voice of the note that started
    // first: as stock does, that note fades out over one block and is then
    // destroyed, and the new note starts in the voice from then on.
    note(5);
    if (destroyed[1] || !block({{0, -1}, {1, 2}, {200, 201}, {5, 6}}) || destroyed[1] != 1) return 13;
    if (!block({{0, 0}, {1, 2}, {200, 201}, {5, 6}})) return 19;
    // A note that still holds its voice keeps it: no new initialize.
    const unsigned before = initialized();
    call(1, 4);
    if (initialized() != before || !block({{1, 2}, {200, 201}, {5, 6}})) return 6;
    // Stock stops rendering index 1 when its note ends. After a whole block
    // without a render its voice is free: the next note takes it.
    if (!block({{200, 201}, {5, 6}}) || !block({{200, 201}, {5, 6}})) return 7;
    note(7);
    if (destroyed[2] != 1 || destroyed[201] || destroyed[6] || !block({{200, 201}, {5, 6}, {7, 8}})) return 8;
    // When every voice sounds, the one stock rendered least recently goes first:
    // 5 has not rendered in this block, though 200 started before it.
    if (!block({{200, 201}, {7, 8}})) return 14;
    // Should the new note render first, the old one has had its block: no fade.
    note(9);
    if (destroyed[6] || !block({{200, 201}, {7, 8}, {9, 10}, {5, 0}}) || destroyed[6] != 1 || destroyed[201]) return 17;
    // A fresh object for an index ends the note its voice held.
    handle[9] = probe_factory(9);
    if (destroyed[10] != 1 || !block({{9, 0}, {200, 201}, {7, 8}})) return 15;
    // Ending a note through the method table still frees its voice, once.
    call(7, 0);
    if (destroyed[8] != 1 || !block({{7, 0}})) return 9;
    call(7, 0);
    if (destroyed[8] != 1) return 16;
    // A long run as stock plays with as many notes as the machine has voices:
    // notes end by going unrendered, a new note takes a free stock index, and
    // when all are busy stock takes one note and restarts on its index (as the
    // OP-XY does once a track reaches its voice limit).
    for (unsigned i = 0; i < 256; ++i) call(i, 0);
    unsigned sounding[2] = {}, count = 0, seed = 1;
    for (unsigned n = 0; n < 20000; ++n) {
        seed = seed * 1103515245u + 12345u;
        if (count && (seed >> 24) % 3 == 0) {
            const unsigned gone = (seed >> 16) % count;
            sounding[gone] = sounding[--count];
        }
        unsigned index = (seed >> 8) % 256;
        while ((count > 0 && sounding[0] == index) || (count > 1 && sounding[1] == index)) index = (index + 1) % 256;
        if (count == 2) index = sounding[(seed >> 4) % 2];
        else sounding[count++] = index;
        note(index);
        // Two blocks pass, as stock renders what sounds. A new note may wait one
        // block, as for a voice stock takes, should notes that ended just before
        // still look sounding; no note that still sounds ever loses its voice.
        for (unsigned b = 0; b < 2; ++b)
            for (unsigned i = 0; i < count; ++i) {
                const opxy::i32 owner = rendered(sounding[i]);
                if (owner != static_cast<opxy::i32>(sounding[i] + 1) && (b || sounding[i] != index || owner)) return 10;
            }
    }
    return 0;
}
