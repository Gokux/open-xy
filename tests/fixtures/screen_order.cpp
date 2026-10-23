// Host contract checks for the compositor traversal (screen_order.cpp.in),
// simulating stock's loop: paint page R7 from [P4++], then the hooked advance.
#include <screen_order.cpp>
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

#define require(value) do { if (!(value)) { std::fprintf(stderr, "line %d\n", __LINE__); std::abort(); } } while (0)

static const opxy::u32 kSlots = 128;
static opxy::u32 owned_page, asked;
static int ready = 1;
int sdk_screen_owned(opxy::u32 page) { ++asked; return page == owned_page ? ready : 0; }

// One frame; returns the pages in paint order. selected changes after the
// first advance to check that the frame keeps its snapshot.
static unsigned frame(opxy::u32 selected, opxy::u32* order) {
    static opxy::u32 slots[kSlots];
    const opxy::u32 base = opxy::u32(reinterpret_cast<__UINTPTR_TYPE__>(slots));
    opxy::platform::ScreenCursor cursor{0, base};
    unsigned count = 0;
    for (;;) {
        require(count < kSlots && cursor.slot == base + cursor.page * 4);
        order[count++] = cursor.page;
        cursor.slot += 4;  // the loop head's post-increment
        const bool more = sdk_screen_next(&cursor, count == 1 ? selected : 127 - selected % 2) != 0;
        if (!more) break;
    }
    require(cursor.page == kSlots);
    return count;
}

int main() {
    opxy::u32 order[kSlots];
    for (int state : {1, 0, 2}) {
        ready = state;
        for (opxy::u32 owned = 0; owned <= kSlots + 1; ++owned)
            for (opxy::u32 selected : {0u, 1u, 2u, 7u, 80u, 81u, 82u, 83u, 126u, 127u, 128u, 200u, owned}) {
                owned_page = owned;
                asked = 0;
                require(frame(selected, order) == kSlots);
                require(asked <= 1);  // ownership is asked once per frame at most
                const bool promoted = ready == 1 && selected == owned && selected > 1 && selected < kSlots;
                // Every page exactly once; the promoted page second, others ascending.
                unsigned expected = 0;
                for (unsigned i = 0; i < kSlots; ++i) {
                    if (promoted && i == 1) { require(order[i] == selected); continue; }
                    if (promoted && expected == selected) ++expected;
                    require(order[i] == expected++);
                }
            }
    }
    std::puts("screen order ok");
    return 0;
}
