// FM ratio control: the modulator's frequency as a multiple of the note's, in
// control order. Shared by the engine and the screen.
#pragma once
namespace macroosc {
struct Ratio { unsigned halves; const char* label; };  // twice the ratio, so 0.5 is 1
static const Ratio ratios[] = {
    {1, "x0.5"}, {2, "x1"}, {3, "x1.5"}, {4, "x2"}, {5, "x2.5"}, {6, "x3"},
    {7, "x3.5"}, {8, "x4"}, {10, "x5"}, {12, "x6"}, {14, "x7"}, {16, "x8"},
};
const unsigned kRatios = sizeof(ratios) / sizeof(ratios[0]);
// The enum control's step, as the definition quantizes Q31 through Q15.
inline const Ratio& RatioFromParameter(int q31) {
  return ratios[q31 < 0 ? 0 : ((static_cast<unsigned>(q31) >> 16) * kRatios) >> 15];
}
}  // namespace macroosc
