#pragma once
#include "types.hpp"
#include <cstring>

namespace opxy {
// Fixed storage, serialized callback ownership. No heap or locks. A stolen
// lease becomes invalid; callers choose silence/restrike rather than retaining
// a dangling resource pointer. Owner IDs are nonzero, stable voice indices.
template<class Resource, u32 Count> struct LeasePool {
    static_assert(Count > 0 && Count <= 256, "Bounded lease capacity required");
    Resource resources[Count];
    u32 owners[Count];
    u32 stamps[Count];
    u32 clock;

    Resource* get(u32 owner, u32 lease) {
        return owner && lease && lease <= Count && owners[lease - 1] == owner
            ? &resources[lease - 1] : nullptr;
    }
    void release(u32 owner, u32 lease) {
        if (get(owner, lease)) owners[lease - 1] = 0;
    }
    u32 acquire(u32 owner, u32 lease) {
        if (!owner) return 0;
        ++clock;
        if (get(owner, lease)) { stamps[lease - 1] = clock; return lease; }
        u32 chosen = 0;
        for (u32 i = 0; i < Count; ++i) {
            if (!owners[i]) { chosen = i; break; }
            if (clock - stamps[i] > clock - stamps[chosen]) chosen = i;
        }
        std::memset(&resources[chosen], 0, sizeof(Resource));
        owners[chosen] = owner;
        stamps[chosen] = clock;
        return chosen + 1;
    }
};
}
