# Display API

Display code runs separately from audio. It emits bounded frames applied by
SDK browser/native renderers to `panel.svg.fragment`. This is retained drawing,
not executable SVG animation. The same C++ computes both previews and device
frames; fonts, framing and rasterization can differ.

Each synth declares its screen in `resources.display` of `definition.json`,
and names the same shape as its C++ frame type. The SDK sizes the native
renderer, the browser renderer and the artwork bindings from that declaration;
a mismatch fails to compile.

## Drawing display

```json
"display": {"kind": "drawing", "stateBytes": 60, "stateAlignment": 4,
            "paths": 2, "points": 64, "nodes": 28, "palette": 16}
```

```cpp
using Frame = opxy::draw::Frame<2, 64, 28, 16>;  // paths, points, nodes, palette
void display_reset(DisplayState& state);
void display(DisplayState& state, const opxy::draw::Input& input, Frame& output);
```

| Field | Limits |
| --- | --- |
| `paths` | 1..4 mutable outlines; they are nodes `0..paths-1` |
| `points` | 2..64 points per outline |
| `nodes` | `paths`..64 transformable nodes |
| `palette` | 1..16 paint donors |
| `stateBytes`, `stateAlignment` | `DisplayState` size (whole words) and alignment, checked against the compiled type |

[draw.hpp](../sdk/include/opxy/draw.hpp) is the format definition.
`DisplayState` is trivial, standard-layout data. Input holds the four Q31
controls, Q10 elapsed seconds, track identity, a uint32 note-start serial and
the reduced-motion preference. A serial is a snapshot, not a queue: several
note starts between frames can coalesce. Initializing or changing track must
not fabricate a note.

The frame persists between calls. Each path has a nonzero geometry key; change
it whenever its points change. The first call after reset must set every path.
Backends cache the keys they applied.

| Field | Bounds |
| --- | --- |
| Path coordinates | ±`path_extent` (64) pixels, Q10 |
| Node x / y | `node_left`..`node_right` / `node_top`..`node_bottom` (-64..640 / -64..320) pixels, Q10 |
| Uniform scale | Positive, at most 2, Q10 |
| Palette selector | Below `palette` |
| Paint | Keep, stroke, or fill-and-stroke |

`hide` moves a node to (`hidden_x`, `hidden_y`), outside the display, while
keeping a positive unit scale.
`valid` checks the complete frame before painting.

Artwork IDs follow the machine's symbol prefix: nodes `<prefix>_node_0` to
`<prefix>_node_<nodes-1>` and palette entries `<prefix>_palette_0` onward. Each
path node is a `path` of exactly `M`, `points - 1` `L` and `Z` with no fill;
other nodes are `path` or `circle`; palette entries have explicit fill, stroke
and stroke width. Fill-and-stroke paint changes a node's fill only when the
artwork gives it one.

## Segment display

```json
"display": {"kind": "segments", "characters": 4, "glow": 3, "dials": 4, "textControls": [0]}
```

```cpp
using Frame = opxy::segments::Frame<4>;  // characters
void display(const opxy::segments::Input& input, Frame& output);
```

| Field | Limits |
| --- | --- |
| `characters` | 1..8 14-segment characters |
| `glow` | 0..3 halo layers drawn under the segments |
| `dials` | 0..4 rotating nodes |
| `textControls` | Distinct control indices 0..3 |

Input holds the four Q31 controls.
[segments.hpp](../sdk/include/opxy/segments.hpp) defines the frame: one
14-segment mask per character (bits 15..2, segments `abcdefghjklmnp`),
`label[16]`, `values[4][8]`, a nonzero key and four dials. Segments, glow and
label repaint when the key changes. For each control listed in `textControls`,
the screen shows `values[i]` in place of the stock value, at three-quarter size;
other controls keep their stock value. Text must terminate within its buffer.

Dials apply every frame. Each is a clockwise rotation from the authored pose as
a Q10 unit vector; `{0, 0}` is the authored pose. `rotation(tenths)` turns by
tenths of a degree and `sweep(control, half)` maps a control onto a sweep of
`half` tenths of a degree either side of the pose (at most 1800).

Artwork IDs are `<prefix>_seg_<character>_<segment>` with the palette donors
`<prefix>_lit` and `<prefix>_unlit`; for each glow layer, outermost first,
`<prefix>_glow_<layer>_<character>_<segment>` with donors
`<prefix>_glow_<layer>_lit` and `<prefix>_glow_<layer>_unlit`; dials
`<prefix>_dial_<i>`; and an optional text node `<prefix>_label` (at most 15
characters). A donor lends its fill, stroke and stroke width. A glow node
repeats its segment's outline: its lit donor's wider stroke is the halo, and
its unlit donor stays within the segment drawn over it. A dial is a filled
path drawn around its pivot at the origin with `transform="matrix(1 0 0 1 x y)"`
placing the pivot.

## Artwork

Use unique node IDs, explicit paint on each leaf and the selected renderer's
expected path topology. Authored numbers allow at most four fractional digits;
exponent notation and unsupported elements/references are rejected. Do not rely
on browser-only SVG features or group style inheritance. The native packager
combines the machine fragment with the SDK-owned
[OP-XY screen template](../sdk/platform/opxy-1.2.0/screen.svg). It supplies a black
480 × 220 canvas and four title/value controls in the top 25 pixels. No stock
artwork is copied. Machine graphics below that header are controlled by
`display.cpp`; the platform adapter updates parameter labels and values.

The template's `titles` and `values` groups each contain four group children,
each with one explicitly styled text leaf. This is the stock four-knob helper's
binding contract. Keep it in the platform layer, shared by machines; a different
device can supply its own platform template and backend. The browser authenticates
the embedded template, while native packaging records it in source provenance.
Template validation checks structure, not actual device text rendering.

See [2op display.cpp](../machines/fm2op/display.cpp) and
[Macro display.cpp](../machines/macroosc/display.cpp) for implementations;
[Macro Osc's artwork](../machines/macroosc/panel.svg.fragment) uses glow and dials.
Stock helper addresses and pointer validation are in the [firmware ABI](abi-1.2.0.md).
