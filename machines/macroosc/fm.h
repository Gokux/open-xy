// FM ratio control: the modulator's frequency as a multiple of the note's, in
// twice the ratio so 0.5 is 1. Shared by the engine and the screen; the steps
// match the FM Ratio enum labels in definition.json, which the browser shows.
#pragma once
namespace macroosc {
static const unsigned char kRatioHalves[] = {1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 14, 16};
const unsigned kRatios = sizeof(kRatioHalves) / sizeof(kRatioHalves[0]);
// The enum control's step, as the definition quantizes Q31 through Q15.
inline unsigned RatioHalvesFromParameter(int q31) {
  return kRatioHalves[q31 < 0 ? 0 : ((static_cast<unsigned>(q31) >> 16) * kRatios) >> 15];
}
}  // namespace macroosc
