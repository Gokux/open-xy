# Machine UX

How a machine looks and behaves on the OP-XY, so every machine plays like part
of one instrument. Catalog review checks machines against these conventions.
[Macro Osc](https://github.com/etcetc000/open-xy-core-machines/tree/main/machines/macroosc)
is the reference for each of them.

## Controls

- **Clockwise goes up.** Turning an encoder clockwise makes its shown number
  rise. Name a control for what rises: Bits counts bits, Rate counts kHz.
- **Defaults are clean.** A new sound starts at the machine's plainest useful
  setting. A control that colours or degrades the sound (crush, drift,
  modulation depth) defaults to off.
- **Real units in the header.** A [header value](display.md#frame) shows what
  the musician thinks in: `2.0` for a ratio, `16` for bits, `11k` for a rate,
  a model's short code. Amounts are 0 to 100 without a percent sign. Keep it
  to about five characters.
- **Short labels.** One or two words, at most eight characters; the stock
  header writes them in lower case.
- **The OP-XY already modulates.** Its envelopes, LFOs, filter and FX have
  their own pages. An engine page holds the sound's own parameters, not
  another envelope, LFO or modulation amount.
- **Fine turns are free.** Shift + turn already gives continuous controls finer
  steps; don't build another.

## More than four controls

- **Two pages.** A synth with five to eight parameters uses
  [`"press": "page"`](api.md#alternate-controls) with all eight: page 1 holds
  what is played most, page 2 the rest. A press of any encoder switches all
  four, so a press means the same thing everywhere.
- **Show the other page.** The stock header shows the page the encoders edit.
  Under it, draw the other page in grey with eight
  [text slots](display.md#frame), on the header's columns:

  | | Titles | Values |
  | --- | --- | --- |
  | x (column `i`) | `5 + 120 i` | `65 + 120 i` |
  | Baseline | 33 px | 33 px |
  | Size | 10 px | 13 px |
  | Fill | `#5A5A5A` | `#707070` |

  Keep the rest of the artwork below about 38 px.
- **Author text at its resting size.** Scaling a text slot is decoration for
  a moment of motion: a layout must read correctly at unit scale.

## Motion

- **Motion answers the player.** Animate what a press, turn or note changed;
  an idle screen stays still.
- **Short and decelerating.** An exponential ease-out that settles within
  0.15 to 0.2 s. A page switch slides the leaving page down from the header
  into the grey row, its values shrinking from 20 to 13 px
  ([Macro Osc's display](https://github.com/etcetc000/open-xy-core-machines/blob/main/machines/macroosc/display.cpp)).
- **Reduced motion jumps.** With `reduced_motion` set, or on a track change,
  show the end state at once.
- **Grey is inactive, bright is active**: the page row, unlit segments, a dial
  not being edited.

## Saved sounds

Projects and presets store all eight parameter slots, and older sounds can
hold 0 in a slot the machine did not declare when they were saved. When a
released machine gains a parameter, make 0 sound as the machine did before, or say in its README which older sounds change and
how to restore them. Existing parameters keep their order and mapping
([definition](api.md#definition)).
