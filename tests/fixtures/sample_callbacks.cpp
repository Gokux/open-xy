#include <sample_callbacks.cpp>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
static unsigned selected = 46, edits;
static bool owned = true;
static opxy::DrumControl received;
extern "C" unsigned sdk_sample_selected_engine() { return selected; }
extern "C" int probe_ready() { return owned; }
// The probe also declares analysis; its callbacks are not exercised here.
extern "C" unsigned probe_analysis_words(const opxy::SampleView*) { return 0; }
extern "C" unsigned probe_prepare_begin(const opxy::SampleView*, unsigned*, unsigned) { return 0; }
extern "C" unsigned probe_prepare_step(unsigned, unsigned*) { return 0; }
extern "C" unsigned probe_prepared(opxy::SampleAnalysis*) { return 0; }
static opxy::SampleAssignment assigned;
extern "C" opxy::PadSettings probe_sample_defaults() { return 77; }
extern "C" opxy::PadSettings probe_sample_assign(const opxy::SampleAssignment* input) {
    assigned = *input; return opxy::PadSettings(input->frames);
}
extern "C" void probe_drum_control(opxy::PadSettings* value, const opxy::DrumControl* event) {
    ++edits; received = *event; ++*value;
}
static const opxy::i32* expected_parameters;
extern "C" void probe_drum_panel(opxy::PadSettings value, const opxy::i32* parameters, opxy::DrumPanel* frame) {
    if (parameters != expected_parameters) std::abort();
    frame->pitch_cents = int(value) - 1200; frame->repeat = value & 1;
    std::memcpy(frame->shifted[0], "first", 6); std::memcpy(frame->shifted[1], "second", 7);
}
static void check(bool value) { if (!value) std::abort(); }
int main() {
    const opxy::SampleAssignment replacement{"095_loop.wav", 12, 1234, 48000, 1200, true, 0xabcd};
    check(sdk_sample_machine(46)->assign(&replacement) == 1234 && assigned.replacing &&
          assigned.previous == 0xabcd && assigned.filename == replacement.filename &&
          assigned.filename_bytes == 12 && assigned.rate == 48000);
    check(sdk_sample_machine(46)->defaults() == 77);
    unsigned raw[8] = {1000, 0, 1000, 0, 1000, 0, 60, 0};
    auto* bytes = reinterpret_cast<unsigned char*>(raw);
    // An unassigned, zero-initialized pad has neutral tuning. Painting must
    // not invent +24 or write a default into the stored record.
    unsigned empty[8] = {}, shadow[8];
    empty[5] = opxy::platform::sample_store_settings(1200);
    unsigned original_empty[8]; std::memcpy(original_empty, empty, sizeof(empty));
    auto* empty_panel = sdk_sample_drum_view(empty, shadow, nullptr);
    check(empty_panel && empty_panel->pitch_cents == 0);
    check(reinterpret_cast<unsigned char*>(shadow)[24] == 60);
    check(std::memcmp(empty, original_empty, sizeof(empty)) == 0);
    check(sdk_sample_edit(empty, 0, 1, 46) == 1);
    empty_panel = sdk_sample_drum_view(empty, shadow, nullptr);
    check(empty_panel && empty_panel->pitch_cents == 10);
    // A root saved by another engine shows the octave the voice plays, not +24.
    unsigned low_root[8]; std::memcpy(low_root, original_empty, sizeof(low_root));
    reinterpret_cast<unsigned char*>(low_root)[24] = 36;
    empty_panel = sdk_sample_drum_view(low_root, shadow, nullptr);
    check(empty_panel && empty_panel->pitch_cents == 1200);
    bytes[27] = 192; bytes[31] = 1;
    for (unsigned index = 0; index < 16; ++index) {
        if (index == 0 || index == 8) continue; // SDK-owned pad pitch/reset.
        raw[5] = opxy::platform::sample_store_settings(123);
        unsigned before[8]; std::memcpy(before, raw, sizeof(raw));
        check(sdk_sample_edit(raw, index, -4, 46) == 1);
        check(opxy::platform::sample_settings(raw[5]).value == 124);
        // A pad without saved settings starts from the machine's defaults.
        raw[5] = 0;
        check(sdk_sample_edit(raw, index, -4, 46) == 1 && opxy::platform::sample_settings(raw[5]).value == 78);
        raw[5] = opxy::platform::sample_store_settings(124);
        check(received.knob == (index & 3) && received.shifted == bool(index & 4) &&
              received.pressed == bool(index & 8) && received.direction == -4);
        before[5] = raw[5]; check(std::memcmp(before, raw, sizeof(raw)) == 0);
    }
    // Sustained pitch edits may change only stock root/fine bytes.
    const unsigned pitch_edits = edits;
    raw[5] = opxy::platform::sample_store_settings(0xabcd);
    for (int direction : {-1, 1}) {
        opxy::platform::sample_gui_pitch(raw, 0);
        for (int step = 1; step <= 140; ++step) {
            unsigned before[8]; std::memcpy(before, raw, sizeof(raw));
            check(sdk_sample_edit(raw, 0, direction * 7, 46) == 1);
            check(opxy::platform::sample_gui_region(raw).pitch_cents == direction * (step > 120 ? 1200 : step * 10));
            auto* old_bytes = reinterpret_cast<unsigned char*>(before);
            old_bytes[24] = bytes[24]; old_bytes[28] = bytes[28];
            check(std::memcmp(before, raw, sizeof(raw)) == 0 && edits == pitch_edits);
        }
        check(sdk_sample_edit(raw, 8, 0, 46) == 1);
        check(opxy::platform::sample_gui_region(raw).pitch_cents == 0);
    }
    // Active-track edits remain valid when the renderer still caches a stock
    // track. Conversely its cached custom track cannot authorize a stock edit.
    selected = 3;
    check(sdk_sample_edit(raw, 0, 1, 46) == 1);
    opxy::platform::sample_gui_pitch(raw, 310);
    selected = 46;
    const unsigned saved = raw[5], count = edits;
    check(sdk_sample_edit(raw, 0, 1, 3) == 0 && raw[5] == saved && edits == count);
    for (unsigned value = 0; value <= 2400; value += 37) {
        static const opxy::i32 parameters[8] = {0x40000000}; expected_parameters = parameters;
        raw[5] = opxy::platform::sample_store_settings(value);
        unsigned original[8]; std::memcpy(original, raw, sizeof(raw));
        unsigned guarded[10] = {0x12345678}; guarded[9] = 0x87654321;
        auto* frame = sdk_sample_drum_view(raw, guarded + 1, parameters);
        check(frame && std::strcmp(frame->shifted[0], "first") == 0 && std::strcmp(frame->shifted[1], "second") == 0);
        const auto* copy = reinterpret_cast<const unsigned char*>(guarded + 1);
        check(frame->pitch_cents == 310 + int(value) - 1200);
        check(int(copy[24]) * 100 + int(copy[28]) == 6000 + 310 + int(value) - 1200);
        check((copy[27] & 63) == ((value & 1) ? 3 : 1) && (copy[27] & 192) == 192 && copy[31] == 1);
        check(guarded[6] == 0 && guarded[0] == 0x12345678 && guarded[9] == 0x87654321);
        check(std::memcmp(raw, original, sizeof(raw)) == 0);
    }
    for (unsigned pass = 0; pass < 2; ++pass) {
        selected = pass ? 3 : 46; owned = pass != 0;
        const unsigned before = raw[5], count = edits;
        check(sdk_sample_edit(raw, 0, 1, selected) == 0 && raw[5] == before && edits == count);
    }
    check(!sdk_sample_edit(nullptr, 0, 1, 46));
    selected = 46; owned = true;
    check(!sdk_sample_edit(raw, 16, 1, 46));
}
