#include "screen_order.hpp"
#include <screen_order.cpp>
#include <cstdio>
#include <cstdlib>

void check(bool yes) { if (!yes) std::abort(); }
unsigned ready = 0, checks = 0;
extern "C" int probe_ready() { ++checks; return ready; }

int main() {
    opxy::screen::Order order = {};
    check(sdk_screen_next(0, 112) == 1 && checks == 1);
    ready = 1;
    check(sdk_screen_next(0, 112) == 112 && checks == 2);
    check(sdk_screen_next(112, 83) == 1 && checks == 2);
    check(sdk_screen_next(111, 83) == 113 && checks == 2);
    check(sdk_screen_next(0, 83) == 1 && checks == 2);
    ready = 2; // Only the exact successful ownership result permits promotion.
    check(sdk_screen_next(0, 112) == 1 && checks == 3);
    for (unsigned owned = 0; owned < 2; ++owned)
        for (unsigned selected = 0; selected <= 130; ++selected) {
            unsigned seen[128] = {}, sequence[128] = {}, current = 0, count = 0;
            while (current < 128) {
                check(count < 128 && !seen[current]);
                seen[current] = 1;
                sequence[count++] = current;
                // Later changes must not change this frame's traversal.
                current = order.next(current, count == 1 ? selected : 127, count == 1 ? owned : !owned);
            }
            check(current == 128 && count == 128);
            unsigned expected = 0;
            const bool promoted = owned && selected > 81 && selected < 128;
            for (unsigned i = 0; i < 128; ++i) {
                check(seen[i] == 1);
                if (promoted && i == 1) { check(sequence[i] == selected); continue; }
                if (promoted && expected == selected) ++expected;
                check(sequence[i] == expected++);
            }
        }
    std::puts("screen order: stock relative order, ownership, one visit per page and frame snapshot passed");
}
