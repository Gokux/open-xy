#pragma once
#include <opxy/sample_engine.hpp>

namespace opxy { namespace platform {
// Tagged, float-round-trippable payload in the stock nonnegative fade word.
inline SampleSettings sample_settings(u32 word) {
    const bool valid = (word & 0xff80007fu) == 0x5a800000u;
    return SampleSettings{valid ? (word >> 7) & 65535u : 0, valid};
}
inline u32 sample_store_settings(u32 value) { return 0x5a800000u | ((value & 65535u) << 7); }
// Keep only pad controls across a file replacement. The new initializer still
// owns duration, outer/inner trims, canonical key and serialized settings.
struct SampleReplacement {
    u32 settings;
    unsigned char root, fine, level, reverse;
    bool assigned;
};
inline SampleReplacement sample_replacement(const void* raw) {
    if (!raw || static_cast<const i32*>(raw)[0] <= 0) return SampleReplacement{};
    const unsigned char* bytes = static_cast<const unsigned char*>(raw);
    return SampleReplacement{static_cast<const u32*>(raw)[5], bytes[24], bytes[28], bytes[29],
                             static_cast<unsigned char>(bytes[31] & 1), true};
}
inline void sample_restore_replacement(void* raw, const SampleReplacement& prior) {
    if (!raw || !prior.assigned) return;
    unsigned char* bytes = static_cast<unsigned char*>(raw);
    bytes[24] = prior.root; bytes[28] = prior.fine; bytes[29] = prior.level;
    bytes[31] = (bytes[31] & 254u) | prior.reverse;
}
// floor(base * (1 + fraction/2^24)), using bounded 12-bit limbs.
inline u32 sample_detune_factor(u32 base, u32 fraction) {
    const u32 mid = ((base >> 12) & 4095u) * fraction, low = (base & 4095u) * fraction;
    return base + (base >> 24) * fraction + (mid >> 12) + (low >> 24) +
           ((((mid & 4095u) << 12) + (low & 0xffffffu)) >> 24);
}
// Stock tuning arrives as inverse-frequency Q16. Decode nearest MIDI cent
// only when it changes; no logarithm or floating point in the audio callback.
static inline i32 sample_root_cents(u32 factor) {
    static const u32 roots[] = {
        353499105u, 333658725u, 314931900u, 297256130u, 280572426u, 264825105u, 249961614u, 235932347u,
        222690482u, 210191825u, 198394665u, 187259628u, 176749553u, 166829362u, 157465950u, 148628065u,
        140286213u, 132412553u, 124980807u, 117966173u, 111345241u, 105095913u, 99197332u, 93629814u,
        88374776u, 83414681u, 78732975u, 74314033u, 70143106u, 66206276u, 62490404u, 58983087u,
        55672620u, 52547956u, 49598666u, 46814907u, 44187388u, 41707341u, 39366487u, 37157016u,
        35071553u, 33103138u, 31245202u, 29491543u, 27836310u, 26273978u, 24799333u, 23407453u,
        22093694u, 20853670u, 19683244u, 18578508u, 17535777u, 16551569u, 15622601u, 14745772u,
        13918155u, 13136989u, 12399667u, 11703727u, 11046847u, 10426835u, 9841622u, 9289254u,
        8767888u, 8275785u, 7811300u, 7372886u, 6959078u, 6568495u, 6199833u, 5851863u,
        5523424u, 5213418u, 4920811u, 4644627u, 4383944u, 4137892u, 3905650u, 3686443u,
        3479539u, 3284247u, 3099917u, 2925932u, 2761712u, 2606709u, 2460405u, 2322314u,
        2191972u, 2068946u, 1952825u, 1843221u, 1739769u, 1642124u, 1549958u, 1462966u,
        1380856u, 1303354u, 1230203u, 1161157u, 1095986u, 1034473u, 976413u, 921611u,
        869885u, 821062u, 774979u, 731483u, 690428u, 651677u, 615101u, 580578u,
        547993u, 517237u, 488206u, 460805u, 434942u, 410531u, 387490u, 365741u,
        345214u, 325839u, 307551u, 290289u, 273997u, 258618u, 244103u, 230403u,
    };
    static const u32 fractions[] = {
        0u, 9694u, 19393u, 29098u, 38808u, 48525u, 58246u, 67974u,
        77707u, 87445u, 97189u, 106939u, 116695u, 126456u, 136223u, 145995u,
        155773u, 165557u, 175346u, 185141u, 194942u, 204748u, 214560u, 224378u,
        234201u, 244030u, 253865u, 263705u, 273551u, 283403u, 293261u, 303124u,
        312993u, 322867u, 332747u, 342633u, 352525u, 362422u, 372325u, 382234u,
        392149u, 402069u, 411995u, 421927u, 431864u, 441808u, 451757u, 461711u,
        471672u, 481638u, 491610u, 501588u, 511571u, 521560u, 531556u, 541556u,
        551563u, 561575u, 571594u, 581617u, 591647u, 601683u, 611724u, 621771u,
        631824u, 641883u, 651948u, 662018u, 672094u, 682176u, 692264u, 702358u,
        712457u, 722563u, 732674u, 742791u, 752914u, 763042u, 773177u, 783317u,
        793464u, 803616u, 813774u, 823938u, 834108u, 844283u, 854465u, 864652u,
        874845u, 885045u, 895250u, 905461u, 915677u, 925900u, 936129u, 946363u,
        956604u, 966850u, 977103u, 987361u, 997625u,
    };
    if (!factor || factor > roots[0] + 128 || factor + 128 < roots[127]) return 6000;
    if (factor > roots[0]) factor = roots[0];
    if (factor < roots[127]) factor = roots[127];
    u32 lo = 0, hi = 127;
    while (lo < hi) { const u32 mid = lo + (hi - lo)/2; if (roots[mid] > factor) lo = mid + 1; else hi = mid; }
    const u32 note = lo;
    lo = 0; hi = 100;
    while (lo < hi) {
        const u32 mid = lo + (hi - lo)/2;
        if (sample_detune_factor(roots[note], fractions[mid]) < factor) lo = mid + 1; else hi = mid;
    }
    if (lo) {
        const u32 a = sample_detune_factor(roots[note], fractions[lo - 1]);
        const u32 b = sample_detune_factor(roots[note], fractions[lo]);
        if (factor >= a && (factor - a <= (factor <= b ? b - factor : factor - b))) --lo;
    }
    return static_cast<i32>(note * 100 - lo);
}

inline u32 sample_marker(i32 value, u32 frames) {
    return value < 0 ? 0 : static_cast<u32>(value) > frames ? frames : static_cast<u32>(value);
}
// GUI records and audio records order their markers differently.
inline SampleRegion sample_gui_region(const void* raw) {
    const unsigned char* bytes = static_cast<const unsigned char*>(raw);
    const i32* words = static_cast<const i32*>(raw);
    const u32 frames = words[0] > 0 ? static_cast<u32>(words[0]) : 0;
    return SampleRegion{sample_marker(words[1], frames),
        words[2] < 0 ? frames : sample_marker(words[2], frames), 0x08000000u,
        (bytes[31] & 1) != 0, !frames && !bytes[24] && !bytes[28] ? 6000 :
        i32(bytes[24]) * 100 - i32(static_cast<const signed char*>(raw)[28]),
        words[5] > 0 ? static_cast<u32>(words[5]) : 0};
}
// Persist pad pitch in stock's root/fine fields, leaving all other metadata
// intact. Audio decodes inverse tuning as root * 100 - signed fine cents.
inline void sample_gui_pitch(void* raw, i32 cents) {
    if (cents < -1200) cents = -1200;
    if (cents > 1200) cents = 1200;
    unsigned char* bytes = static_cast<unsigned char*>(raw);
    const i32 root = (6000 - cents + 99) / 100;
    bytes[24] = static_cast<unsigned char>(root);
    bytes[28] = static_cast<unsigned char>(root * 100 - (6000 - cents));
}
// Stock note-start (8d519f40 / 8d51a09c): parameter 52 spans -36..36.
inline i32 sample_track_transpose(i32 value) {
    if (value < 0) value = 0;
    return i32(((u32(value) >> 8) * 73u) >> 23) - 36;
}
// Same 24-pad map as stock 8d5b6800, using an already-published octave.
// This arithmetic helper is safe in audio: it does not access GUI projects.
inline u32 sample_drum_key(u32 key, i32 octave) {
    return 53u + static_cast<u32>((i32(key) + 19 + 12 * (octave % 2)) % 24);
}
inline SampleRegion sample_region(const i32* words, u32 frames, i32 root_cents, bool outer_only = false) {
    SampleRegion result{0, frames, 0x08000000u, false, root_cents, 0};
    if (!words) return result;
    result.begin = sample_marker(words[0], frames);
    result.end = words[3] == -1 ? frames : sample_marker(words[3], frames);
    if (!outer_only && !(words[4] & 4)) {
        const u32 inner_begin = sample_marker(words[1], frames);
        if (inner_begin > result.begin) result.begin = inner_begin;
        if (words[2] != -1) {
            const u32 inner_end = sample_marker(words[2], frames);
            if (inner_end < result.end) result.end = inner_end;
        }
    }
    result.fade_q31 = words[6] > 0 ? static_cast<u32>(words[6]) : 0;
    result.reverse = (words[4] & 1) != 0;
    result.level = words[7] > 0 ? static_cast<u32>(words[7]) : 0;
    return result;
}
}}
