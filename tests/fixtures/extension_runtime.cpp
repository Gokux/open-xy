#include <extension_runtime.cpp>
#define CHECK(value) do { if (!(value)) return __LINE__; } while (false)
using namespace opxy;
using namespace opxy::platform;
namespace {
RecordingContext stock_context = {1, 2, 0, 7680, 3, 255, true};
bool playing = true;
u32 writes, notices, observations, order[16], order_count, result, mode;
extensions::Actions saved;
extensions::Context saved_context;
const RecordedNote good = {-12, 60, 60, 100};
void first_note(const extensions::Context&, const extensions::LiveNote& note) {
    order[order_count++] = 1;
    observations += note.position == -12 && note.collision_radius == 180;
    // Reentrant callbacks are ignored, not delivered out of order.
    extensions_recordable_note_on(0, 60, 100);
}
void second_note(const extensions::Context&, const extensions::LiveNote&) { order[order_count++] = 2; }
void observe_control(const extensions::Context& context, const extensions::Control&, const extensions::Actions& actions) {
    result = actions.insert_notes(context, &good, 1);
    actions.notify("unauthorized");
}
void edit_control(const extensions::Context& context, const extensions::Control&, const extensions::Actions& actions) {
    saved = actions; saved_context = context;
    RecordedNote note = good;
    if (mode == 1) ++stock_context.pattern;
    if (mode == 2) note.pitch = 128;
    if (mode == 3) note.position = -241;
    if (mode == 4) note.length = stock_context.length + 1;
    result = mode == 6 ? actions.replace_notes(context, &note, 1) : actions.insert_notes(context, &note, 1);
    actions.notify("done");
    actions.notify("duplicate");
    if (mode == 5) result += actions.insert_notes(context, &good, 1);
    if (mode == 7) result += actions.replace_notes(context, &good, 1);  // one write per callback
}
const extensions::Hooks first = {nullptr, first_note, nullptr, nullptr, nullptr, observe_control};
const extensions::Hooks second = {nullptr, second_note, nullptr, nullptr, nullptr, edit_control};
// Two claims on different keys; edit_notes needs the first, or any claim once set to 0.
u32 claim_keys[] = {50, 51}, action_claims[] = {1u};
const ExtensionRegistry tables = {claim_keys, 2, action_claims, 1};
ExtensionEntry collection[] = {{"observer", 0, 0, &first}, {"writer", 1u, action_edit_notes, &second}};
}
namespace opxy { namespace platform {
const ExtensionEntry* extension_collection(u32& count) { count = 2; return collection; }
const ExtensionRegistry& extension_registry() { return tables; }
RecordingContext extension_context(bool& p) { p = playing; return stock_context; }
i32 extension_position(u32) { return -12; }
u32 extension_scaled_delta(u32, u32 delta) { return delta << 8; }
i32 extension_collision_radius(u32) { return 180; }
bool replaced;
u32 extension_write(u32, const RecordedNote*, u32 count, bool replace) { ++writes; replaced = replace; return count; }
void extension_notify(const char*) { ++notices; }
}}
void control(u32 key, bool accepted) {
    const extensions::Control event = {key, false, accepted, true, 100};
    extensions_queued_control(event);
}
int main() {
    extensions_recordable_note_on(0, 60, 100);
    CHECK(order_count == 2 && order[0] == 1 && order[1] == 2 && observations == 1);
    extensions_recordable_note_on(7, 60, 100); CHECK(order_count == 2);
    control(50, true);
    CHECK(writes == 1 && notices == 1 && result == 1);
    CHECK(saved.insert_notes(saved_context, &good, 1) == 0);
    saved.notify("late"); CHECK(notices == 1);
    for (mode = 1; mode <= 4; ++mode) {
        control(50, true);
        CHECK(result == 0 && writes == 1 && notices == 1);
    }
    mode = 5;
    control(50, true);
    CHECK(result == 1 && writes == 2 && notices == 2 && !replaced);
    mode = 6;
    control(50, true);
    CHECK(result == 1 && writes == 3 && replaced);
    mode = 7;
    control(50, true);
    CHECK(result == 1 && writes == 4 && !replaced);
    mode = 0;
    control(50, false);
    control(12, true);
    CHECK(result == 0 && writes == 4 && notices == 4);
    // Guard the generated registry at runtime as well as build time.
    initialized = false; entries = nullptr; collection[0].claims = 1u;
    extensions_recordable_note_on(0, 60, 100); CHECK(order_count == 2);
    initialized = false; collection[0].claims = 0; collection[0].actions = action_edit_notes;
    extensions_recordable_note_on(0, 60, 100); CHECK(order_count == 2);
    initialized = false; collection[0].actions = 0; collection[0].id = "writer";
    extensions_recordable_note_on(0, 60, 100); CHECK(order_count == 2);
    // A second claim, on key 51, grants the same action with no runtime change.
    initialized = false; entries = nullptr; collection[0].actions = 0; collection[0].id = "observer";
    collection[1].claims = 2u; action_claims[0] = 0;  // edit_notes: any claim its holder owns
    mode = 0; const u32 before = writes;
    control(50, true); CHECK(writes == before);
    control(51, true); CHECK(writes == before + 1);
    control(51, false); CHECK(writes == before + 1);
    // An action whose claim its holder lacks disables the collection.
    initialized = false; entries = nullptr; action_claims[0] = 1u;
    control(51, true); CHECK(writes == before + 1);
    return 0;
}
