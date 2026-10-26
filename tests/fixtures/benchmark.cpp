#include <cstdlib>
#include <cstring>
#include <benchmark.cpp>

namespace {
Test stock_tests[9];
unsigned calls, available = 1, lose_after_stock;
void need(bool value) { if (!value) std::abort(); }
void benchmark_one(void* controller, const Test* test, u32 index, u32 total) {
    need(controller == reinterpret_cast<void*>(0x84c70fac));
    need(index == calls && total == 9 + available);
    if (calls < 9) need(test == &stock_tests[calls]);
    else {
        need(std::strcmp(test->name, "unfamiliar") == 0);
        need(test->engine == static_cast<u32>(reinterpret_cast<Address>(unfamiliar_engine_id)));
        need(test->setup == 19 && test->parameter == 0x40000000);
    }
    ++calls;
}
}

extern "C" {
const char unfamiliar_engine_id[] = "engine";
int unfamiliar_ready() { return available && !(lose_after_stock && calls >= 9); }
}

namespace opxy { namespace platform {
Address host_stock_address(Address address) {
    if (address == 0x8409bf18) return reinterpret_cast<Address>(stock_tests);
    if (address == 0x8d57b8f0) return reinterpret_cast<Address>(benchmark_one);
    need(address == 0x84c70fac);
    return address;
}
}}

int main() {
    sdk_benchmark_run(); need(calls == 10);
    calls = 0; available = 0;
    sdk_benchmark_run(); need(calls == 9);
    calls = 0; available = 1; lose_after_stock = 1;
    sdk_benchmark_run(); need(calls == 9);
}
