// Shared display behavior. The SDK applies this bounded frame to retained
// segment paths, glow, dials and inline text in the browser and the native renderer.
#include <opxy/segments.hpp>
#include "fm.h"
#include "models.hpp"

namespace macroosc {
// Four characters; the model code replaces the first control's value, and the
// fourth shows the FM ratio or, after a press of its encoder, the FM depth.
using Frame = opxy::segments::Frame<4>;
// The knobs turn 144 degrees either side of 12 o'clock, end to end of their ticks.
const opxy::i32 kSweep = 1440;
const unsigned kModels = sizeof(models) / sizeof(models[0]);
const unsigned kRatioSlot = 3;
// A whole percentage, 0..100, rounded as the preview shows it.
inline void percent(char* out, unsigned capacity, opxy::i32 value) {
  unsigned p = value < 0 ? 0 : ((static_cast<unsigned>(value) >> 8) * 100 + (1u << 22)) >> 23;
  char text[5];
  unsigned n = 0;
  if (p >= 100) text[n++] = '1';
  if (p >= 10) text[n++] = static_cast<char>('0' + p / 10 % 10);
  text[n++] = static_cast<char>('0' + p % 10);
  text[n++] = '%';
  text[n] = 0;
  opxy::segments::text(out, capacity, text);
}
// The FM ratio as its enum label: 0.5, 1, 1.5 ... 8.
inline void ratio(char* out, unsigned capacity, unsigned halves) {
  char text[4] = {static_cast<char>('0' + halves / 2), 0, 0, 0};
  if (halves & 1) {
    text[1] = '.';
    text[2] = '5';
  }
  opxy::segments::text(out, capacity, text);
}
inline void display(const opxy::segments::Input& input, Frame& frame) {
  const opxy::i32 model = input.parameters[0];
  unsigned index = model < 0 ? 0 : ((static_cast<unsigned>(model) >> 16) * kModels) >> 15;
  for (unsigned i = 0; i < 4; ++i)
    frame.masks[i] = models[index].masks[i];
  opxy::segments::text(frame.label, sizeof(frame.label), models[index].label);
  opxy::segments::text(frame.values[0], sizeof(frame.values[0]), models[index].code);
  if (input.shown[3] == kRatioSlot)
    ratio(frame.values[3], sizeof(frame.values[3]), RatioHalvesFromParameter(input.parameters[3]));
  else
    percent(frame.values[3], sizeof(frame.values[3]), input.parameters[3]);
  frame.key = index + 1;
  // The model knob steps between models; the others turn continuously.
  frame.dials[0] = opxy::segments::rotation(-kSweep + static_cast<opxy::i32>(index) * 2 * kSweep / (kModels - 1));
  for (unsigned i = 1; i < 4; ++i)
    frame.dials[i] = opxy::segments::sweep(input.parameters[i], kSweep);
}
}  // namespace macroosc
