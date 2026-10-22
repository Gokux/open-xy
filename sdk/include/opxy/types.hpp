#pragma once

namespace opxy {
// Compiler-provided widths avoid depending on a target C library.
using i32 = __INT32_TYPE__;
using u32 = __UINT32_TYPE__;
using u16 = __UINT16_TYPE__;
using i64 = __INT64_TYPE__;
static_assert(sizeof(i32) == 4 && sizeof(u32) == 4, "32-bit audio words required");
}
