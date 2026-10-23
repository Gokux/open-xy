#pragma once
#include "types.hpp"

namespace opxy { namespace draw {
// Retained drawing: the machine declares its frame shape in definition.json
// (resources.display) and names the same shape here, e.g.
//   using Frame = opxy::draw::Frame<2, 64, 28, 16>;
// Coordinates and uniform scale are Q10; palette selectors index the asset's
// own palette entries.
const i32 unit = q10_unit;
// Bounds in pixels. Path points are relative to their node; node positions
// cover the screen plus a margin, so a node can be parked out of view.
const i32 path_extent = 64;
const i32 node_left = -64, node_right = 640, node_top = -64, node_bottom = 320;
const i32 hidden_x = 640, hidden_y = 120;
enum Paint : u32 { keep = 0, stroke = 1, fill_and_stroke = 2 };
struct Point { i32 x, y; };
template <u32 Points> struct Path { u32 key; Point points[Points]; };
struct Node { i32 x, y, scale; u32 shade; Paint paint; };
// Paths are nodes 0..Paths-1: mutable outlines of exactly Points points.
template <u32 Paths, u32 Points, u32 Nodes, u32 Palette>
struct Frame {
    static const u32 path_count = Paths;
    static const u32 point_count = Points;
    static const u32 node_count = Nodes;
    static const u32 palette_count = Palette;
    using path_type = draw::Path<Points>;
    path_type paths[Paths];
    Node nodes[Nodes];
};
struct Input {
    i32 parameters[page_controls];
    i32 elapsed;             // Q10 seconds; the author clamps late/invalid frames.
    u32 track;               // Track identity, not a device address.
    u32 note_serial;         // Snapshot, not an event queue; wraps modulo 2^32.
    u32 reduced_motion;
    u8 shown[page_controls];  // Declared parameter shown at each position, as in segments::Input.
};

// Defined floor division by 1024 on both compilers, including negative values.
// Callers keep products inside int32. No floating point or runtime division.
inline i32 floor_q10(i32 value) {
    return value / unit - (value < 0 && value % unit != 0);
}
inline i32 clamp(i32 value, i32 low, i32 high) {
    return value < low ? low : value > high ? high : value;
}
template <class F>
inline void place(F& frame, u32 node, i32 x, i32 y, i32 scale, u32 shade, Paint paint) {
    if (node >= F::node_count) return;
    Node& destination = frame.nodes[node];
    destination.x = x;
    destination.y = y;
    destination.scale = scale;
    destination.shade = shade;
    destination.paint = paint;
}
// Positive unit scale avoids singular matrices in the stock renderer.
template <class F>
inline void hide(F& frame, u32 node) {
    place(frame, node, hidden_x * unit, hidden_y * unit, unit, 0, keep);
}
// Both backends check the complete frame before applying it.
template <class F>
inline bool valid(const F& frame) {
    for (u32 p = 0; p < F::path_count; ++p) {
        if (!frame.paths[p].key) return false;
        for (u32 i = 0; i < F::point_count; ++i) {
            const Point& point = frame.paths[p].points[i];
            if (point.x < -path_extent * unit || point.x > path_extent * unit ||
                point.y < -path_extent * unit || point.y > path_extent * unit) return false;
        }
    }
    for (u32 i = 0; i < F::node_count; ++i) {
        const Node& node = frame.nodes[i];
        if (node.x < node_left * unit || node.x > node_right * unit ||
            node.y < node_top * unit || node.y > node_bottom * unit ||
            node.scale <= 0 || node.scale > 2 * unit ||
            node.shade >= F::palette_count || node.paint > fill_and_stroke) return false;
    }
    return true;
}
}} // namespace opxy::draw
