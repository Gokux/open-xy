// Shared display behavior. The SDK applies this bounded frame to retained
// segment paths, glow, dials and inline text in the browser and the native renderer.
#include <opxy/segments.hpp>
#include "fm.h"
#include "models.hpp"

namespace macroosc {
// Four characters show the model; its code replaces the first control's value,
// and the fourth shows the FM ratio or, after a press of its encoder, the FM depth.
using Frame = opxy::segments::Frame<4>;
// The knobs turn 144 degrees either side of 12 o'clock, end to end of their ticks.
const opxy::i32 kSweep = 1440;
const unsigned kModels = sizeof(models) / sizeof(models[0]);
// Parameter slots (definition.json).
const unsigned kModelSlot = 0, kTimbreSlot = 1, kColorSlot = 2, kRatioSlot = 3, kDepthSlot = 4;
// One decimal place, matching fine turns and the browser preview.
inline void amount(char* out, unsigned capacity, opxy::i32 value) {
  unsigned p = value < 0 ? 0 : ((static_cast<unsigned>(value) >> 10) * 1000 + (1u << 20)) >> 21;
  char text[6];
  unsigned n = 0;
  if (p >= 1000) text[n++] = '1';
  if (p >= 100) text[n++] = static_cast<char>('0' + p / 100 % 10);
  text[n++] = static_cast<char>('0' + p / 10 % 10);
  text[n++] = '.';
  text[n++] = static_cast<char>('0' + p % 10);
  text[n] = 0;
  opxy::segments::text(out, capacity, text);
}
// One decimal place; audio retains the full interpolated Q16 ratio.
inline void ratio(char* out, unsigned capacity, unsigned q16) {
  const unsigned tenths = (q16 * 10 + 32768) >> 16;
  char text[4] = {static_cast<char>('0' + tenths / 10), '.', static_cast<char>('0' + tenths % 10), 0};
  opxy::segments::text(out, capacity, text);
}
inline void display(const opxy::segments::Input& input, Frame& frame) {
  const opxy::i32 model = input.slots[kModelSlot];
  unsigned index = model < 0 ? 0 : ((static_cast<unsigned>(model) >> 16) * kModels) >> 15;
  for (unsigned i = 0; i < 4; ++i)
    frame.masks[i] = models[index].masks[i];
  opxy::segments::text(frame.label, sizeof(frame.label), models[index].label);
  opxy::segments::text(frame.values[0], sizeof(frame.values[0]), models[index].code);
  amount(frame.values[1], sizeof(frame.values[1]), input.parameters[1]);
  amount(frame.values[2], sizeof(frame.values[2]), input.parameters[2]);
  if (input.shown[3] == kRatioSlot)
    ratio(frame.values[3], sizeof(frame.values[3]), RatioQ16FromParameter(input.parameters[3]));
  else
    amount(frame.values[3], sizeof(frame.values[3]), input.parameters[3]);
  frame.key = index + 1;
  // Knobs: Timbre and Color along the bottom; on the right, the linked pair
  // the fourth encoder switches between, each showing its own parameter: FM
  // Ratio below, stepping between ratios, and FM Depth above.
  frame.dials[0] = opxy::segments::sweep(input.slots[kTimbreSlot], kSweep);
  frame.dials[1] = opxy::segments::sweep(input.slots[kColorSlot], kSweep);
  frame.dials[2] = opxy::segments::sweep(input.slots[kRatioSlot], kSweep);
  frame.dials[3] = opxy::segments::sweep(input.slots[kDepthSlot], kSweep);
}
}  // namespace macroosc
