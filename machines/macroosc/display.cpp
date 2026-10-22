// Shared display behavior. The SDK applies this bounded frame to retained
// segment paths, glow, dials and inline text in the browser and the native renderer.
#include <opxy/segments.hpp>
#include "models.hpp"

namespace macroosc {
// Four characters; the model code replaces the first control's value.
using Frame = opxy::segments::Frame<4>;
// The knobs turn 144 degrees either side of 12 o'clock, end to end of their ticks.
const opxy::i32 kSweep = 1440;
const unsigned kModels = sizeof(models) / sizeof(models[0]);
inline void display(const opxy::segments::Input& input, Frame& frame) {
  const opxy::i32 model = input.parameters[0];
  unsigned index = model < 0 ? 0 : ((static_cast<unsigned>(model) >> 16) * kModels) >> 15;
  for (unsigned i = 0; i < 4; ++i)
    frame.masks[i] = models[index].masks[i];
  opxy::segments::text(frame.label, sizeof(frame.label), models[index].label);
  opxy::segments::text(frame.values[0], sizeof(frame.values[0]), models[index].code);
  frame.key = index + 1;
  // The model knob steps between models; the others turn continuously.
  frame.dials[0] = opxy::segments::rotation(-kSweep + static_cast<opxy::i32>(index) * 2 * kSweep / (kModels - 1));
  for (unsigned i = 1; i < 4; ++i)
    frame.dials[i] = opxy::segments::sweep(input.parameters[i], kSweep);
}
}  // namespace macroosc
