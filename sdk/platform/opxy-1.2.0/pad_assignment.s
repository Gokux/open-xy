/* Pad assignment hooks whose register contract C++ cannot express: two retry
 * hooks that replace literal loads inside stock functions, and the fade
 * conversion inside the region initializer, which delivers a result in R4.
 * The decisions and the owned initializer call are C++ in
 * pad_assignment_stock.cpp.
 */
.include "sdk/platform/opxy-1.2.0/hook.inc"
.section .text
.align 2
.extern sdk_sample_retry

/* Replaces a literal load whose register \reg the stub reloads with \high:\low.
 * R0 is a stock path-equality result; sdk_sample_retry clears it when an owned
 * pad may retry. Returns CC = R0 == 0, as stock tests next. */
.macro RETRY name, pending, reg, high, low
.global \name
.type \name, STT_FUNC
\name:
    HOOK_SAVE
    R1 = \pending;
    CALL sdk_sample_retry;
    HOOK_RESULT R0
    HOOK_RESTORE
    CC = R0 == 0;
    \reg\().H = \high;
    \reg\().L = \low;
    RTS;
.size \name, .-\name
.endm

/* 8c0a219c: active-file equality. Returning to the active file after queuing
 * another must update the pending request, or its stale path equality
 * discards A in A/B/A. */
RETRY sdk_sample_active_retry, 0, P4, 0x0801, 0xf7dc
/* 8c0a21c0: pending-path equality. A stale header completion retries the
 * pending path, which stock's duplicate check drops even with the worker idle. */
RETRY sdk_sample_pending_retry, 1, R5, 0x0801, 0xf7c0

/* 8d5882d8: the region initializer's fade conversion. While C++ runs the owned
 * initializer call it publishes sdk_sample_assigning {active, settings, key}:
 * the stub returns the settings in R0 and the canonical key in R4, which stock
 * stores next. Any other initializer call keeps stock's conversion. */
.global sdk_sample_assign_fade
.type sdk_sample_assign_fade, STT_FUNC
sdk_sample_assign_fade:
    P0.H = sdk_sample_assigning;
    P0.L = sdk_sample_assigning;
    R1 = [P0];
    CC = R1 == 0;
    IF CC JUMP .Lassign_fade_stock;
    R4 = [P0 + 8];
    R0 = [P0 + 4];
    RTS;
.Lassign_fade_stock:
    LINK 12;
    P0 = 0x04020fd8;
    CALL (P0);
    UNLINK;
    RTS;
.size sdk_sample_assign_fade, .-sdk_sample_assign_fade
