// Host boundary double for the real synth control adapter's enum steps and
// presses and labels: stock's step-count query, its encoder edit and the GUI state they
// read. The machines are table rows; no machine behavior is tested.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <synth_controls.cpp>

namespace {
using opxy::i32;
using opxy::u32;

void require(bool condition, const char* message) {
    if (!condition) { std::fprintf(stderr, "%s\n", message); std::exit(1); }
}

const u32 kBlocks = 0x90000000, kBlockBytes = 0x10000;
u32 engines[16], bases[8][8], stock_presses, stock_asks;
u32 vtable = kInstrumentController, page, selected;
// The last stock edit.
u32 edits, edit_track, edit_index;
i32 edit_event[3];

u32 stock_engine(u32 track) { return track < 16 ? engines[track] : 0; }
u32 stock_steps(u32 track, u32 index, u32* scale) {
    ++stock_asks;
    *scale = track + index;  // a marker the adapter must pass through untouched
    return 0xffffffff;
}
u32 stock_edit(u32 project, u32 track, u32 index, const i32* event) {
    require(project == kProject, "Edit outside the project");
    ++edits;
    edit_track = track;
    edit_index = index;
    for (u32 i = 0; i < 3; ++i) edit_event[i] = event[i];
    return 0;
}
void stock_press(u32) { ++stock_presses; }
u32* stock_top() { return &vtable; }
u32 stock_track_data(u32 track) { return kBlocks + track * kBlockBytes; }
u32 stock_shift() { return 0; }
u32 stock_selected() { return selected; }
int ready() { return 1; }
bool format(u32, i32, char*) { return false; }

// The value stock stores for choice `index` of `count`: the bucket's centre.
i32 centre(u32 index, u32 count) {
    const u32 q = 0x7fffffffu / count;
    return static_cast<i32>(index * q + q / 2);
}
u32 choice(i32 value, u32 count) { return ((static_cast<u32>(value) >> 16) * count) >> 15; }

void press(u32 encoder) {
    edits = 0;
    sdk_synth_press(encoder);
}
}

extern "C" {
// Engine 40: a synth whose slot 0 is a three-choice enum that a press steps,
// slot 2 a 17-choice enum and slot 3 a 256-choice one stock steps itself;
// slot 1 is continuous. Effect 8 has a four-choice enum in slot 1.
const opxy::platform::SynthControls sdk_synth_controls[] = {
    {reinterpret_cast<const char*>(40), ready, {0, 1, 2, 3, 4, 5, 6, 7}, 0x2, {3, 0, 17, 0, 0, 0, 0, 0}, 0x1, format, false},
    {reinterpret_cast<const char*>(8), ready, {0, 1, 2, 3, 4, 5, 6, 7}, 0xd, {0, 4, 0, 0, 0, 0, 0, 0}, 0, format, true},
    {nullptr, nullptr, {0, 1, 2, 3, 4, 5, 6, 7}, 0, {0, 0, 0, 0, 0, 0, 0, 0}, 0, nullptr, false}};
const opxy::u32 sdk_synth_control_count = 2;
}

opxy::platform::Address opxy::platform::host_stock_address(opxy::platform::Address address) {
    if (address == 0x8d585eb4) return reinterpret_cast<Address>(&stock_engine);
    if (address == 0x8c0b2fc8) return reinterpret_cast<Address>(&stock_steps);
    if (address == 0x8d5ab8ec) return reinterpret_cast<Address>(&stock_edit);
    if (address == 0x8d51e634) return reinterpret_cast<Address>(&stock_press);
    if (address == 0x8c095008) return reinterpret_cast<Address>(&stock_top);
    if (address == 0x8d585da0) return reinterpret_cast<Address>(&stock_track_data);
    if (address == 0x8d51e5bc) return reinterpret_cast<Address>(&stock_shift);
    if (address == 0x8d4d78cc) return reinterpret_cast<Address>(&stock_selected);
    if (address == kInstrumentPage) return reinterpret_cast<Address>(&page);
    if (address == kSelectedTrack) return reinterpret_cast<Address>(&selected);
    if (address >= kBlocks + 0x3864 && address < kBlocks + 8 * kBlockBytes) {
        const u32 track = (address - kBlocks) / kBlockBytes, at = address - kBlocks - track * kBlockBytes - 0x3864;
        if (at < sizeof(bases[0])) return reinterpret_cast<Address>(&bases[track][at / 4]);
    }
    std::abort();
}

int main() {
    engines[2] = 40;
    engines[14] = 8;
    u32 scale = 2;
    // Owned enum slots answer their choice count with scale 1.
    require(sdk_param_steps(2, 0, &scale) == 3 && scale == 1 && stock_asks == 0, "Synth enum not stepped");
    scale = 2;
    require(sdk_param_steps(2, 2, &scale) == 17 && scale == 1, "Second enum not stepped");
    require(sdk_param_steps(14, 1, &scale) == 4 && scale == 1, "Effect enum not stepped");
    // Continuous and oversized slots, other tracks and other engines ask stock.
    const u32 asked[][2] = {{2, 1}, {2, 3}, {2, 8}, {3, 0}, {14, 0}, {15, 1}, {9, 0}};
    for (const auto& a : asked) {
        scale = 2;
        const u32 before = stock_asks;
        require(sdk_param_steps(a[0], a[1], &scale) == 0xffffffff && stock_asks == before + 1 &&
                    scale == a[0] + a[1], "Stock step count not delegated");
    }

    // A press of position 0 selects the next choice, wrapping, through stock's edit.
    selected = 2;
    for (u32 index = 0; index < 3; ++index) {
        bases[2][0] = static_cast<u32>(centre(index, 3));
        press(0);
        require(edits == 1 && edit_track == 2 && edit_index == 0, "Press not edited");
        require(edit_event[0] == 0 && edit_event[2] == 0, "Press not a slow detent");
        // One detent up, or from the last choice back to the first.
        require(choice(centre(index, 3), 3) == index && edit_event[1] == (index < 2 ? 1 : -2), "Press not the next choice");
    }
    require(stock_presses == 3, "Stock press not delegated");
    // Positions without press, other pages, controllers and engines don't edit.
    press(2);
    require(edits == 0, "Press edited a position without press");
    page = 1;
    press(0);
    require(edits == 0, "Press edited off the engine page");
    page = 0;
    vtable = 0;
    press(0);
    require(edits == 0, "Press edited under another controller");
    vtable = kInstrumentController;
    selected = 3;
    press(0);
    require(edits == 0, "Press edited another engine");
    require(stock_presses == 7, "Stock press skipped");

    // The label shown is the choice a stored value selects, the one a press
    // starts from: every bucket's centre and both edges, negative values first.
    const char* const labels[] = {"play", "wr a", "wr b"};
    char text[16];
    for (u32 index = 0; index < 3; ++index) {
        opxy::platform::control_label(text, centre(index, 3), labels, 3);
        require(std::strcmp(text, labels[index]) == 0, "Label not the stored choice");
    }
    opxy::platform::control_label(text, -1, labels, 3);
    require(std::strcmp(text, "play") == 0, "Negative value not the first label");
    opxy::platform::control_label(text, 0x7fffffff, labels, 3);
    require(std::strcmp(text, "wr b") == 0, "Full value not the last label");
    for (u32 count = 2; count <= 256; ++count)
        for (u32 index = 0; index < count; ++index)
            require(opxy::platform::control_choice(centre(index, count), count) == index, "Choice not the stored bucket");
    std::puts("synth steps ok");
    return 0;
}
