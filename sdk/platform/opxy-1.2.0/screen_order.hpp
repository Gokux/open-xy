// GUI compositor traversal. Stock screen numbers encode layer order; extended
// synth pages must paint before stock overlays without changing their identity.
#pragma once
#include "opxy/types.hpp"

namespace opxy { namespace screen {
struct Order {
    u32 promoted;

    u32 next(u32 current, u32 selected, bool owned) {
        // Capture once per frame; an absent/conflicting registration keeps the
        // original ascending traversal. Page 81 is the stock none sentinel.
        if (current == 0)
            promoted = owned && selected > 81 && selected < 128 ? selected : 0;
        if (promoted) {
            if (current == 0) return promoted;
            if (current == promoted) return 1;
            if (current + 1 == promoted) return current + 2;
        }
        return current + 1;
    }
};
}} // namespace opxy::screen
