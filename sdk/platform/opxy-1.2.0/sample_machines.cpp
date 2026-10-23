// Stock sample dispatch for every registered SDK sample engine. A matching
// engine number is not enough: the machine's registration must still be ours.
// The stubs in sample_hooks.s call these from inside stock functions.
#include "sample_machines.hpp"

using opxy::u32;
using opxy::platform::SampleMachine;

extern "C" {
u32 sdk_sample_page(u32) __asm__("sdk_sample_page");
u32 sdk_sample_alias(u32) __asm__("sdk_sample_alias");
}

const SampleMachine* sdk_sample_machine(u32 engine) {
    for (u32 i = 0; i < sdk_sample_machine_count; ++i) {
        const SampleMachine& m = sdk_sample_machines[i];
        if (m.engine == engine) return m.ready() == 1 ? &m : nullptr;
    }
    return nullptr;
}

// Note-region hook: the owned machine's stock page (2 or 7), or 0.
u32 sdk_sample_page(u32 engine) { return opxy::platform::sample_page(engine); }

// Stock's sample predicates know only stock engine IDs. Owned SDK engines
// borrow the multisampler's (30) payload; the track keeps the real engine.
u32 sdk_sample_alias(u32 engine) { return sdk_sample_page(engine) ? 30 : engine; }
