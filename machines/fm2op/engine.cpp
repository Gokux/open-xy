#include "core.h"
#include "opxy/q31.hpp"
#include "tables.h"

namespace fm2op {
namespace {

using opxy::q31::multiply;
using opxy::q31::half;

inline i32 nonnegative(i32 value) { return value < 0 ? 0 : value; }

inline i32 sine(u32 phase) {
    const u32 index = phase >> 22;
    const i32 fraction = static_cast<i32>((phase & 0x3fffffu) << 9);
    return fm2op_sine_table[index] + multiply(
        fm2op_sine_table[index + 1] - fm2op_sine_table[index], fraction);
}

struct Targets {
    i32 ratio, amount, feedback, decay;
    explicit Targets(const i32* parameters) {
        const u32 position = static_cast<u32>(
            multiply(nonnegative(parameters[0]), FM2_RATIO_POSITION_SCALE));
        const u32 index = position >> 26;
        ratio = fm2op_ratios[index] + multiply(fm2op_ratios[index + 1] - fm2op_ratios[index],
            static_cast<i32>((position & 0x3ffffffu) << 5));
        const i32 a = nonnegative(parameters[1]);
        const i32 f = nonnegative(parameters[2]);
        amount = multiply(multiply(a, a), FM2_AMOUNT_SCALE);
        feedback = multiply(multiply(f, f), FM2_FEEDBACK_SCALE);
        const u32 d = static_cast<u32>(nonnegative(parameters[3]));
        const u32 di = d >> 23;
        decay = fm2op_decay[di] + multiply(fm2op_decay[di + 1] - fm2op_decay[di],
            static_cast<i32>((d & 0x7fffffu) << 8));
    }
};

inline void smooth(i32& current, i32 target) {
    current += multiply(target - current, FM2_SMOOTH);
}
}

// Each note starts from silence: phases, feedback history and brightness reset.
inline void start(Voice& voice, Shared&, u32) {
    Voice* v = &voice;
    v->carrier_phase = v->modulator_phase = 0;
    v->last_modulator = v->previous_modulator = 0;
    v->brightness = opxy::q31::maximum;
    v->initialized = 0;
    v->ratio = v->amount = v->feedback = v->decay = 0;
}
inline void initialize(Voice& voice, Shared& shared, u32 owner) { start(voice, shared, owner); }
inline void destroy(Voice&, Shared&, u32) {}

inline void render(Voice& voice, Shared&, u32, opxy::Output output,
                   opxy::Parameters parameters, opxy::Pitch pitch) {
    Voice* v = &voice;
    const Targets target(parameters);
    if (!v->initialized) {
        v->ratio = target.ratio;
        v->amount = target.amount;
        v->feedback = target.feedback;
        v->decay = target.decay;
        v->initialized = 1;
    }
    for (unsigned i = 0; i != opxy::block_frames; ++i) {
        smooth(v->ratio, target.ratio);
        smooth(v->amount, target.amount);
        smooth(v->feedback, target.feedback);
        smooth(v->decay, target.decay);
        const i32 history = half(v->last_modulator) + half(v->previous_modulator);
        const u32 feedback = static_cast<u32>(multiply(history, v->feedback)) << 1;
        const i32 modulator = sine(v->modulator_phase + feedback);
        v->previous_modulator = v->last_modulator;
        v->last_modulator = modulator;
        const u32 offset = static_cast<u32>(
            multiply(multiply(modulator, v->brightness), v->amount)) << 3;
        output[i] = half(sine(v->carrier_phase + offset));
        v->brightness = multiply(v->brightness, v->decay);
        const u32 increment = pitch[i];
        v->carrier_phase += increment;
        v->modulator_phase += static_cast<u32>(
            multiply(static_cast<i32>(increment >> 1), v->ratio)) << 6;
    }
}

} // namespace fm2op
