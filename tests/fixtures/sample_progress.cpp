// Host contract checks for the actual GUI policy with stock-boundary doubles.
#include <cstring>
#include <cstdio>
#include <cstdlib>

static bool context = true;
static bool active;
static char popup[64];
static unsigned publications;
static unsigned duration;
extern "C" int sdk_sample_progress_context() { return context; }
extern "C" int sdk_sample_popup_active() { return active; }
extern "C" int sdk_sample_popup_matches(const char* text, unsigned size) {
    return std::strlen(popup) == size && std::strcmp(popup, text) == 0;
}
extern "C" void sdk_sample_popup_publish(const char* text, unsigned seconds) {
    std::strcpy(popup, text); active = true; duration = seconds; ++publications;
}
extern "C" void sdk_sample_progress_update(unsigned, unsigned, unsigned);
static void require(bool value) { if (!value) std::abort(); }

int main() {
    // Lifecycle states must not disturb the user's current popup.
    sdk_sample_progress_update(0, 0, 1);
    sdk_sample_progress_update(2, 100, 1);
    sdk_sample_progress_update(99, 0, 1);
    require(publications == 0);
    context = false;
    sdk_sample_progress_update(1, 0, 1);
    require(publications == 0);
    context = true;
    std::strcpy(popup, "Saving project"); active = true;
    sdk_sample_progress_update(1, 0, 1);
    require(publications == 0 && std::strcmp(popup, "Saving project") == 0);
    active = false;
    for (unsigned value = 0; value <= 101; ++value) {
        char expected[32];
        std::snprintf(expected, sizeof(expected), "Preparing sample %u%%",
                      value > 100 ? 100 : value);
        sdk_sample_progress_update(1, value, 1);
        require(std::strcmp(popup, expected) == 0 && duration == 0x3f000000u);
    }
    const unsigned count = publications;
    // A system message replacing our active message wins immediately.
    std::strcpy(popup, "Battery low");
    sdk_sample_progress_update(1, 40, 1);
    sdk_sample_progress_update(3, 40, 1);
    require(publications == count && std::strcmp(popup, "Battery low") == 0);
    active = false;
    sdk_sample_progress_update(3, 40, 1);
    require(publications == count + 1 && std::strcmp(popup, "Sample failed") == 0 &&
            duration == 0x40400000u);
    active = false;
    sdk_sample_progress_update(3, 40, 1);
    require(publications == count + 1); // Failed job does not notify forever.
    sdk_sample_progress_update(3, 40, 2);
    require(publications == count + 2); // A new failed request can notify again.
    const unsigned done = publications;
    sdk_sample_progress_update(2, 100, 2);
    require(publications == done); // Completion relies on TTL, never global hide.
    active = false;
    sdk_sample_progress_update(4, 0, 3);
    require(publications == done + 1 && std::strcmp(popup, "Sample cache full") == 0);
    active = false;
    sdk_sample_progress_update(4, 0, 3);
    require(publications == done + 1);
    std::puts("Timestretch progress policy: lifecycle/ownership/format checks passed");
}
