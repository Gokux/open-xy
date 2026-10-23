// Segment display renderer: 14-segment characters with glow layers, dials, a
// label and text in place of chosen control values. Segments, glow and label
// repaint only when the frame key changes; text controls and dials are set
// every frame. Include after the generated segment_binding.hpp.
#pragma once
#include "screen.hpp"

namespace opxy { namespace screen { namespace {
// The machine's input and frame; never accessed by audio callbacks.
segments::Input segment_input;
binding::SegmentFrame segment_frame;

// Machine: glow layers, dials, a text_controls bit mask, and ids[] naming the
// bound nodes (segments character-major in abcdefghjklmnp order, then each glow
// layer's, then the dials), the label, then each layer's lit/unlit donors.
template <class Machine> struct Segments {
    typedef binding::SegmentFrame Frame;
    enum { characters = Frame::character_count, cells = 14 * characters, glow = Machine::glow,
           dials = Machine::dials, layers = 1 + glow, bound = cells * layers + dials };
    static_assert(dials <= 4 && Machine::text_controls < 16, "Segment display shape");
    static_assert(sizeof(Machine::ids) / sizeof(Machine::ids[0]) == bound + 1 + 2 * layers, "Segment artwork IDs");
    struct Object {
        Base base;
        PathNode* nodes[bound];  // path leaves, or 0 when missing or foreign
        Leaf* label;             // text leaf, or 0
        u32 styles[layers][2];   // packed lit/unlit palette IDs of the segments, then each glow layer
        u32 last;                // last painted key, ~0 for none
    };

    static void init(Object* o) {
        clear(o);
        o->last = ~0u;
        if (!o->base.svg) return;
        bind_controls(&o->base);
        // All header values use approximately 12 px (60% of the template's
        // 20 px), including stock-backed percentages. Decimal captions such
        // as 100.0% must fit the same column as model codes and FM ratios.
        for (u32 i = 0; i < 4; ++i) {
            Leaf* value = text_node(o->base.values[i]);
            if (!value) continue;
            const i32 matrix[9] = {614, 0, 0, 0, 614, 0, static_cast<i32>(50 + 120 * i) * 1024, 18 * 1024, 1024};
            set_matrix(value, matrix);
        }
        for (u32 i = 0; i < bound; ++i) o->nodes[i] = path_node(find(&o->base, Machine::ids[i]));
        o->label = text_node(find(&o->base, Machine::ids[bound]));
        for (u32 i = 0; i < layers; ++i)
            for (u32 j = 0; j < 2; ++j)
                o->styles[i][j] = palette_ids(find(&o->base, Machine::ids[bound + 1 + 2 * i + j]), o->base.svg);
    }

    // Segment s of a character is lit when mask bit 15 - s is set.
    static void paint_model(Object* o) {
        PathNode* const* node = o->nodes;
        for (u32 layer = 0; layer < layers; ++layer)
            for (u32 c = 0; c < characters; ++c)
                for (u32 s = 0; s < 14; ++s)
                    paint(*node++, o->styles[layer][segment_frame.masks[c] << s & 0x8000 ? 0 : 1], true);
        if (o->label) set_text(o->label, segment_frame.label);
    }

    // A dial's rotation replaces its matrix's linear part and keeps its
    // translation; {0, 0} is the authored pose (identity).
    static void dial(PathNode* node, const segments::Dial& d) {
        if (!node) return;
        const i32 cos = d.cos | d.sin ? d.cos : 1024, sin = d.sin;
        const u32 at[4] = {0, 1, 3, 4};
        const i32 value[4] = {cos, sin, -sin, cos};
        set_words(&node->leaf, at, value);
    }

    static void frame(Object* o, i32) {
        Controls controls;
        if (!refresh_controls(&o->base, controls)) return;
        for (u32 i = 0; i < page_controls; ++i) {
            segment_input.parameters[i] = controls.values[i];
            segment_input.shown[i] = controls.shown[i];
        }
        for (u32 i = 0; i < parameter_slots; ++i) segment_input.slots[i] = controls.slots[i];
        if (controls.valid && binding::segment_render(&segment_input, &segment_frame)) {
            for (u32 i = 0; i < 4; ++i)
                if (Machine::text_controls >> i & 1)
                    if (Leaf* value = text_node(o->base.values[i])) set_text(value, segment_frame.values[i]);
            for (u32 i = 0; i < dials; ++i) dial(o->nodes[cells * layers + i], segment_frame.dials[i]);
            if (o->last != segment_frame.key) {
                paint_model(o);
                o->last = segment_frame.key;
            }
        }
        draw(&o->base);
    }
};
}}} // namespace opxy::screen::<unnamed>
