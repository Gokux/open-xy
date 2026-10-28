// Stock OS 1.2.1 project companions (docs/projects.md). Stock saves every project,
// the workspace included, through one call of save(project, path) (8d599074, from
// 8d585eda). After a save that succeeds, the hook writes the .oxy beside the .xy: the
// saved file's size and CRC-32, then this firmware's machine numbers, in the canonical
// form tooling/projects.py writes. It runs where stock saves, never on the audio role.
// A failure leaves the previous companion, which no longer matches, or a partial
// one; readers ignore both.
//
// Stock loads every project, the workspace included, through load_project (8d5890b0),
// which deserializes the file into the inactive project buffer with one call of
// deserialize(project, path) (8d599b10, from 8d58913e), then validates it and makes it
// pending. That call is hooked too: after a load that succeeds, the reader opens the
// .oxy beside the .xy, requires its binding to match the file's size and CRC-32, and
// maps each number its open-xy.machines section lists, by machine ID, to this
// firmware's number in every pattern of the instrument tracks (engines) and send
// tracks (effects). Any problem leaves the project as saved; the load never fails
// because of its companion.
#include "project_companion.hpp"
#include "stock.hpp"

using opxy::u32;
using opxy::platform::CompanionMachine;
using opxy::platform::stock;

extern "C" u32 sdk_project_save(void* project, const char* path) __asm__("sdk_project_save");
extern "C" u32 sdk_project_load(void* project, const char* path) __asm__("sdk_project_load");

namespace {
typedef void File;
// newlib, as stock's project reader and writer call it (8d590d7c, 8d590e28, 8d591304, 8d590da2).
File* file_open(const char* path, const char* mode) {
    return stock<File*(const char*, const char*)>(0x8fed0348)(path, mode);
}
u32 file_read(void* data, u32 size, u32 count, File* file) {
    return stock<u32(void*, u32, u32, File*)>(0x8fed05bc)(data, size, count, file);
}
u32 file_write(const void* data, u32 size, u32 count, File* file) {
    return stock<u32(const void*, u32, u32, File*)>(0x8fed0780)(data, size, count, file);
}
void file_close(File* file) { stock<int(File*)>(0x8fed00ae)(file); }
u32 save(void* project, const char* path) { return stock<u32(void*, const char*)>(0x8d599074)(project, path); }
u32 deserialize(void* project, const char* path) {
    return stock<u32(void*, const char*)>(0x8d599b10)(project, path);
}

const u32 kPathBytes = 256;
const u32 kTextBytes = 8192;
const u32 kChunkBytes = 4096;
// The writer's and the reader's buffers stay apart, so a save and a load never share one.
unsigned char chunk[kChunkBytes];
char text[kTextBytes];
char companion[kPathBytes];
unsigned char read_chunk[kChunkBytes];
char read_companion_path[kPathBytes];
u32 crc_table[256];

u32 value(const char* symbol) { return static_cast<u32>(reinterpret_cast<__UINTPTR_TYPE__>(symbol)); }

// zlib's CRC-32.
u32 crc32(u32 crc, const unsigned char* data, u32 count) {
    if (!crc_table[1]) {
        for (u32 i = 0; i < 256; ++i) {
            u32 c = i;
            for (int bit = 0; bit < 8; ++bit) c = c & 1 ? 0xedb88320u ^ (c >> 1) : c >> 1;
            crc_table[i] = c;
        }
    }
    crc = ~crc;
    while (count--) crc = crc_table[(crc ^ *data++) & 0xff] ^ (crc >> 8);
    return ~crc;
}

// The project's bytes as saved: false when it cannot be read back.
bool measure(const char* path, unsigned char* buffer, u32& bytes, u32& crc) {
    File* file = file_open(path, "rb");
    if (!file) return false;
    bytes = crc = 0;
    for (u32 count; (count = file_read(buffer, 1, kChunkBytes, file)) != 0;) {
        crc = crc32(crc, buffer, count);
        bytes += count;
    }
    file_close(file);
    return true;
}

// song.xy -> song.oxy; false for any other name.
bool companion_path(const char* path, char* out) {
    u32 length = 0;
    while (path[length]) ++length;
    if (length < 4 || length + 2 >= kPathBytes || path[length - 3] != '.' || path[length - 2] != 'x' ||
        path[length - 1] != 'y')
        return false;
    for (u32 i = 0; i < length - 2; ++i) out[i] = path[i];
    out[length - 2] = 'o';
    out[length - 1] = 'x';
    out[length] = 'y';
    out[length + 1] = 0;
    return true;
}

class Writer {
public:
    u32 length = 0;
    bool full = false;
    void put(const char* s) { while (*s) byte(*s++); }
    void byte(char c) {
        if (length < kTextBytes) text[length++] = c;
        else full = true;
    }
    void number(u32 v) {
        char digits[10];
        u32 count = 0;
        do { digits[count++] = static_cast<char>('0' + v % 10); v /= 10; } while (v);
        while (count) byte(digits[--count]);
    }
    void hex(u32 v) {
        for (int shift = 28; shift >= 0; shift -= 4) byte("0123456789abcdef"[(v >> shift) & 15]);
    }
};

void write_companion(u32 bytes, u32 crc) {
    Writer w;
    w.put("{\n  \"format\": \"open-xy-project\",\n  \"project\": {\n    \"bytes\": ");
    w.number(bytes);
    w.put(",\n    \"crc32\": \"");
    w.hex(crc);
    w.put("\"\n  },\n  \"sections\": {\n    \"open-xy.machines\": {\n      \"machines\": {");
    u32 listed = 0;
    for (const CompanionMachine* m = sdk_companion_machines; m->id; ++m) {
        const u32 number = value(m->number);
        if (!number) continue;  // a kit machine this selection left out
        w.put(listed++ ? ",\n        \"" : "\n        \"");
        w.put(m->id);
        w.put(m->effect ? "\": {\n          \"effect\": " : "\": {\n          \"engine\": ");
        w.number(number);
        w.put(",\n          \"page\": ");
        w.number(value(m->page));
        w.put("\n        }");
    }
    w.put(listed ? "\n      },\n" : "},\n");
    w.put("      \"profile\": \"opxy-1.2.1\",\n      \"version\": 1\n    }\n  },\n  \"version\": 1\n}\n");
    if (w.full) return;
    File* file = file_open(companion, "wb");
    if (!file) return;
    file_write(text, w.length, 1, file);
    file_close(file);
}

// Reading, as tooling/projects.py parse() and translation() do. The document streams
// through read_chunk, so a companion of up to 64 KiB needs no buffer of its size.
const u32 kCompanionLimit = 64 * 1024;
// Engine and effect records (docs/abi-1.2.1.md): no registered number lies outside.
const u32 kNumbers = 63;
// A number the companion does not list stays as saved (a stock machine).
const u32 kUnlisted = 0xfffffffeu;
// What a listed machine this firmware lacks becomes. Stock's registry checks (8d50534e,
// 8d5052fc) reject a negative number before their bound, so the validator that runs
// right after the load always replaces it with Prism (18) or no effect (0), and never
// opens whatever this firmware's layout gave the old number. Leaving a free old number
// would fall back the same way; rewriting every missing one needs no proof it is free.
// Follow-up: nothing yet tells the user which machine was missing (docs/projects.md).
const u32 kUnregistered = 0xffffffffu;
const u32 kDepth = 8;      // nesting a skipped value may use; deeper is refused (stack)
const u32 kKeyBytes = 64;  // longer strings match nothing we read

// Old number -> this firmware's number, kUnlisted or kUnregistered, for engines (tracks
// 0-7) and effects (send tracks 14 and 15), which share the pattern field.
u32 engine_map[kNumbers];
u32 effect_map[kNumbers];

class Source {
public:
    explicit Source(File* file) : file_(file) {}
    // The next byte, or -1 at the end or past the 64 KiB limit.
    int peek() {
        if (at_ == have_) {
            if (ended_) return -1;
            at_ = 0;
            have_ = file_read(read_chunk, 1, kChunkBytes, file_);
            total_ += have_;
            if (!have_ || total_ > kCompanionLimit) {
                ended_ = true;
                over_ = total_ > kCompanionLimit;
                have_ = 0;
                return -1;
            }
        }
        return read_chunk[at_];
    }
    int next() {
        const int c = peek();
        if (c >= 0) ++at_;
        return c;
    }
    bool over() const { return over_; }

private:
    File* file_;
    u32 at_ = 0, have_ = 0, total_ = 0;
    bool ended_ = false, over_ = false;
};

bool digit(int c) { return c >= '0' && c <= '9'; }

// A string's decoded UTF-8: its length, and its first kKeyBytes bytes.
struct Text {
    char bytes[kKeyBytes];
    u32 length;
    bool is(const char* s) const {
        u32 n = 0;
        while (s[n]) ++n;
        if (n != length) return false;
        for (u32 i = 0; i < n; ++i)
            if (bytes[i] != s[i]) return false;
        return true;
    }
};

// A JSON number: integer when it has no fraction or exponent; the magnitude saturates.
struct Number {
    bool integer, negative;
    u32 magnitude;
};

// A strict JSON (RFC 8259) reader over the stream, building no document tree.
class Parser {
public:
    explicit Parser(File* file) : source_(file) {}

    int peek() {
        for (int c = source_.peek(); c == ' ' || c == '\t' || c == '\n' || c == '\r'; c = source_.peek())
            source_.next();
        return source_.peek();
    }
    bool at_number() {
        const int c = peek();
        return c == '-' || digit(c);
    }
    // Only whitespace remains, within the limit.
    bool end() { return peek() < 0 && !source_.over(); }

    bool string(Text& text) {
        text.length = 0;
        if (peek() != '"') return false;
        source_.next();
        for (;;) {
            const int c = source_.next();
            if (c < 0x20) return false;  // a control character, or the end
            if (c == '"') return true;
            u32 code = static_cast<u32>(c);
            if (c == '\\') {
                switch (source_.next()) {
                case '"': code = '"'; break;
                case '\\': code = '\\'; break;
                case '/': code = '/'; break;
                case 'b': code = 8; break;
                case 'f': code = 12; break;
                case 'n': code = 10; break;
                case 'r': code = 13; break;
                case 't': code = 9; break;
                case 'u':
                    if (!hex4(code)) return false;
                    if (code >= 0xd800 && code < 0xdc00 && source_.peek() == '\\') {
                        source_.next();
                        u32 low;
                        if (source_.next() != 'u' || !hex4(low)) return false;
                        if (low >= 0xdc00 && low < 0xe000) {
                            code = 0x10000 + ((code - 0xd800) << 10) + (low - 0xdc00);
                        } else {
                            put(text, code);  // a lone half, kept as Python keeps it
                            code = low;
                        }
                    }
                    break;
                default: return false;
                }
            } else if (c >= 0x80) {
                u32 follow, least;
                if (c >= 0xc2 && c <= 0xdf) follow = 1, least = 0x80, code = c & 0x1f;
                else if (c >= 0xe0 && c <= 0xef) follow = 2, least = 0x800, code = c & 0x0f;
                else if (c >= 0xf0 && c <= 0xf4) follow = 3, least = 0x10000, code = c & 0x07;
                else return false;
                while (follow--) {
                    const int d = source_.next();
                    if (d < 0 || (d & 0xc0) != 0x80) return false;
                    code = code << 6 | (d & 0x3f);
                }
                if (code < least || code > 0x10ffff || (code >= 0xd800 && code < 0xe000)) return false;
            }
            put(text, code);
        }
    }

    bool number(Number& n) {
        n.integer = true;
        n.negative = false;
        n.magnitude = 0;
        if (peek() == '-') {
            source_.next();
            n.negative = true;
        }
        const int first = source_.next();
        if (!digit(first)) return false;
        n.magnitude = static_cast<u32>(first - '0');
        if (first != '0') {
            while (digit(source_.peek())) {
                const u32 d = static_cast<u32>(source_.next() - '0');
                n.magnitude = n.magnitude > (0xffffffffu - d) / 10 ? 0xffffffffu : n.magnitude * 10 + d;
            }
        }
        if (source_.peek() == '.') {
            source_.next();
            n.integer = false;
            if (!digit(source_.peek())) return false;
            while (digit(source_.peek())) source_.next();
        }
        if (source_.peek() == 'e' || source_.peek() == 'E') {
            source_.next();
            n.integer = false;
            if (source_.peek() == '+' || source_.peek() == '-') source_.next();
            if (!digit(source_.peek())) return false;
            while (digit(source_.peek())) source_.next();
        }
        return true;
    }

    // An integer member: false only for malformed JSON; `ok` says it is a non-negative
    // integer (Python's `type(n) is int`, booleans excluded).
    bool natural(u32& value, bool& ok) {
        ok = false;
        if (!at_number()) return skip();
        Number n;
        if (!number(n)) return false;
        ok = n.integer && !n.negative;
        value = n.magnitude;
        return true;
    }

    // Any value, checked and discarded.
    bool skip(u32 depth = kDepth) {
        const int c = peek();
        if (c == '"') {
            Text text;
            return string(text);
        }
        if (c == '-' || digit(c)) {
            Number n;
            return number(n);
        }
        if (c == 't') return word("true");
        if (c == 'f') return word("false");
        if (c == 'n') return word("null");
        if (!depth) return false;
        if (c == '{') return object([&](const Text&) { return skip(depth - 1); });
        if (c != '[') return false;
        source_.next();
        if (peek() == ']') {
            source_.next();
            return true;
        }
        for (;;) {
            if (!skip(depth - 1)) return false;
            const int s = peek();
            source_.next();
            if (s == ']') return true;
            if (s != ',') return false;
        }
    }

    // An object, calling member(key) with the reader at each member's value, which it
    // must read. A repeated key is read again, so the last one decides, as in Python.
    template <class Member> bool object(Member member) {
        if (peek() != '{') return false;
        source_.next();
        if (peek() == '}') {
            source_.next();
            return true;
        }
        for (;;) {
            Text key;
            if (!string(key) || peek() != ':') return false;
            source_.next();
            if (!member(key)) return false;
            const int s = peek();
            source_.next();
            if (s == '}') return true;
            if (s != ',') return false;
        }
    }

private:
    Source source_;

    bool word(const char* s) {
        while (*s)
            if (source_.next() != *s++) return false;
        return true;
    }
    bool hex4(u32& code) {
        code = 0;
        for (int i = 0; i < 4; ++i) {
            const int c = source_.next();
            const int v = c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 :
                          c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (v < 0) return false;
            code = code << 4 | static_cast<u32>(v);
        }
        return true;
    }
    static void put(Text& text, u32 code) {
        unsigned char utf8[4];
        u32 n = 0;
        if (code < 0x80) {
            utf8[n++] = static_cast<unsigned char>(code);
        } else {
            const u32 follow = code < 0x800 ? 1 : code < 0x10000 ? 2 : 3;
            utf8[n++] = static_cast<unsigned char>((0xff00u >> (follow + 1)) | code >> (6 * follow));
            for (u32 i = follow; i--;) utf8[n++] = static_cast<unsigned char>(0x80 | (code >> (6 * i) & 0x3f));
        }
        for (u32 i = 0; i < n; ++i, ++text.length)
            if (text.length < kKeyBytes) text.bytes[text.length] = static_cast<char>(utf8[i]);
    }
};

bool lower_or_digit(char c) { return (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9'); }

// owner.name (tooling/projects.py SECTION_NAME); bounded: longer names are refused.
bool section_name(const Text& name) {
    if (name.length > kKeyBytes) return false;
    u32 parts = 0;
    for (u32 i = 0; i < name.length;) {
        if (!lower_or_digit(name.bytes[i])) return false;
        while (i < name.length && (lower_or_digit(name.bytes[i]) || name.bytes[i] == '-')) ++i;
        ++parts;
        if (i < name.length && (name.bytes[i++] != '.' || i == name.length)) return false;
    }
    return parts >= 2;
}

// A machine ID (tooling/definitions.py stock_name): a lowercase letter, then letters,
// digits or _, at most 15 characters.
bool machine_name(const Text& name) {
    if (name.length < 1 || name.length > 15 || name.bytes[0] < 'a' || name.bytes[0] > 'z') return false;
    for (u32 i = 1; i < name.length; ++i)
        if (!lower_or_digit(name.bytes[i]) && name.bytes[i] != '_') return false;
    return true;
}

// This firmware's number for the machine, or kUnregistered when it lacks it (a kit
// machine left out has number 0) or holds it as the other kind.
u32 number_here(const Text& id, bool effect) {
    for (const CompanionMachine* m = sdk_companion_machines; m->id; ++m)
        if (id.is(m->id) && m->effect == effect && value(m->number)) return value(m->number);
    return kUnregistered;
}

void list(bool effect, u32 old, u32 here) {
    if (old >= kNumbers) return;  // no pattern holds such a number registered
    u32& slot = (effect ? effect_map : engine_map)[old];
    // Two machines listed at one number: neither can be trusted.
    slot = slot == kUnlisted || slot == here ? here : kUnregistered;
}

void clear_maps() {
    for (u32 i = 0; i < kNumbers; ++i) engine_map[i] = effect_map[i] = kUnlisted;
}

// One machine of open-xy.machines: false only for malformed JSON; `valid` cleared when
// it is not an engine and page, or an effect and page, each an integer.
bool machine_entry(Parser& p, const Text& id, bool& valid) {
    if (!machine_name(id) || p.peek() != '{') {
        valid = false;
        return p.skip();
    }
    bool engine = false, effect = false, page = false, ints = true;
    u32 number = 0;
    const bool read = p.object([&](const Text& field) {
        bool ok;
        if (field.is("page")) {
            page = true;
            if (p.at_number()) {
                Number n;
                if (!p.number(n)) return false;
                ok = n.integer;
            } else {
                ok = false;
                if (!p.skip()) return false;
            }
            ints = ints && ok;
            return true;
        }
        if (!field.is("engine") && !field.is("effect")) {
            valid = false;
            return p.skip();
        }
        (field.is("engine") ? engine : effect) = true;
        if (!p.at_number()) {
            ints = false;
            return p.skip();
        }
        Number n;
        if (!p.number(n)) return false;
        ints = ints && n.integer;
        number = n.negative ? kUnlisted : n.magnitude;  // negative: never a registered number
        return true;
    });
    if (!read) return false;
    if (!ints || !page || engine == effect) valid = false;
    else list(effect, number, number_here(id, effect));
    return true;
}

// open-xy.machines, version 1: false when it is invalid, which makes the whole
// companion ignored. `applies` is set when its profile is this firmware's, the maps
// then holding its numbers; a newer version is ignored and leaves them empty.
bool machines_section(Parser& p, bool& applies) {
    bool have_version = false, have_profile = false, same_profile = false, have_machines = false, valid = true;
    u32 version = 0;
    applies = false;
    clear_maps();
    const bool read = p.object([&](const Text& key) {
        if (key.is("version")) {
            if (!p.natural(version, have_version)) return false;
            have_version = have_version && version >= 1;
            return true;
        }
        if (key.is("profile")) {
            have_profile = p.peek() == '"';
            if (!have_profile) return p.skip();
            Text profile;
            if (!p.string(profile)) return false;
            same_profile = profile.is("opxy-1.2.1");
            return true;
        }
        if (!key.is("machines")) return p.skip();
        clear_maps();
        valid = true;
        have_machines = p.peek() == '{';
        if (!have_machines) return p.skip();
        return p.object([&](const Text& id) { return machine_entry(p, id, valid); });
    });
    if (!read || !have_version) return false;
    if (version > 1) {  // a newer section: ignored, the rest of the companion used
        clear_maps();
        return true;
    }
    if (!valid || !have_profile || !have_machines) return false;
    applies = same_profile;
    return true;
}

// The project binding: false only for malformed JSON.
bool binding_member(Parser& p, u32& bytes, u32& crc, bool& valid) {
    bool have_bytes = false, have_crc = false;
    valid = false;
    if (p.peek() != '{') return p.skip();
    const bool read = p.object([&](const Text& field) {
        if (field.is("bytes")) return p.natural(bytes, have_bytes);
        if (!field.is("crc32")) return p.skip();
        have_crc = p.peek() == '"';
        if (!have_crc) return p.skip();
        Text text;
        if (!p.string(text)) return false;
        have_crc = text.length == 8;
        crc = 0;
        for (u32 i = 0; have_crc && i < 8; ++i) {
            const char c = text.bytes[i];
            have_crc = digit(c) || (c >= 'a' && c <= 'f');
            crc = crc << 4 | static_cast<u32>(digit(c) ? c - '0' : c - 'a' + 10);
        }
        return true;
    });
    valid = have_bytes && have_crc;
    return read;
}

// Any other owner's section: an object with a positive integer version.
bool other_section(Parser& p) {
    bool positive = false;
    u32 version = 0;
    const bool read = p.object([&](const Text& field) {
        if (!field.is("version")) return p.skip();
        return p.natural(version, positive);
    });
    return read && positive && version >= 1;
}

// Reads the companion: true when it is valid and its machines section applies to this
// firmware, the maps then filled, with the binding it gives.
bool read_document(File* file, u32& bytes, u32& crc) {
    Parser p(file);
    bool format = false, version = false, binding = false, sections = false, applies = false;
    clear_maps();
    const bool read = p.object([&](const Text& key) {
        if (key.is("format")) {
            format = p.peek() == '"';
            if (!format) return p.skip();
            Text text;
            if (!p.string(text)) return false;
            format = text.is("open-xy-project");
            return true;
        }
        if (key.is("version")) {
            u32 number = 0;
            if (!p.natural(number, version)) return false;
            version = version && number == 1;  // 0 is invalid; a newer envelope is ignored
            return true;
        }
        if (key.is("project")) return binding_member(p, bytes, crc, binding);
        if (!key.is("sections")) return p.skip();
        applies = false;
        clear_maps();
        sections = p.peek() == '{';
        if (!sections) return p.skip();
        return p.object([&](const Text& name) {
            if (!section_name(name) || p.peek() != '{') return false;
            return name.is("open-xy.machines") ? machines_section(p, applies) : other_section(p);
        });
    });
    return read && p.end() && format && version && binding && sections && applies;
}

// Rewrites every pattern's machine number on the instrument and send tracks
// (docs/abi-1.2.1.md, project companions).
void remap(unsigned char* project) {
    for (u32 track = 0; track < 16; ++track) {
        if (track >= 8 && track < 14) continue;  // tracks 8-13 hold no machine number
        const u32* map = track < 8 ? engine_map : effect_map;
        unsigned char* base = project + 0xd7c + track * 0x53f44;
        u32 patterns = *reinterpret_cast<u32*>(base + 0x53f40);
        if (patterns > 16) patterns = 16;
        for (u32 k = 0; k < patterns; ++k) {
            u32& number = *reinterpret_cast<u32*>(base + k * 0x53f4 + 0x18);
            if (number < kNumbers && map[number] != kUnlisted) number = map[number];
        }
    }
}

void apply_companion(void* project, const char* path) {
    if (!companion_path(path, read_companion_path)) return;
    File* file = file_open(read_companion_path, "rb");
    if (!file) return;  // no companion: the numbers are read as saved
    u32 bytes = 0, crc = 0, measured_bytes, measured_crc;
    const bool applies = read_document(file, bytes, crc);
    file_close(file);
    // Saved since by stock or another tool, for other firmware, or invalid: as saved.
    if (!applies || !measure(path, read_chunk, measured_bytes, measured_crc) || measured_bytes != bytes ||
        measured_crc != crc)
        return;
    remap(static_cast<unsigned char*>(project));
}
}

u32 sdk_project_save(void* project, const char* path) {
    const u32 saved = save(project, path);
    u32 bytes, crc;
    if (saved && path && companion_path(path, companion) && measure(path, chunk, bytes, crc))
        write_companion(bytes, crc);
    return saved;
}

// Stock's deserialize, then the companion's numbers. The project is the inactive buffer,
// which nothing reads until stock validates it and makes it pending.
u32 sdk_project_load(void* project, const char* path) {
    const u32 loaded = deserialize(project, path);
    if (loaded && project && path) apply_companion(project, path);
    return loaded;
}
