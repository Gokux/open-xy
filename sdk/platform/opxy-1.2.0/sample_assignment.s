/* Sample assignment entries that cannot be C++: two retry hooks that replace
 * instructions inside stock functions, and the owned region initializer call,
 * whose return address and frame the fade hook recognizes. The rest is in
 * sample_assignment_stock.cpp. */
.section .text
.align 2
.extern sdk_sample_retry_owned

/* 8c0a219c replaces a literal load: R0 is the active-file equality result.
 * Returning to the active file after queuing another must update the pending
 * request, or its stale path equality discards A in A/B/A. Clear the result
 * when an owned page's generations differ; replay P4 and keep every register. */
.global sdk_sample_active_retry
.type sdk_sample_active_retry, STT_FUNC
sdk_sample_active_retry:
    LINK 44;
    [SP + 12] = R0;
    [SP + 16] = R1;
    [SP + 20] = R2;
    [SP + 24] = R3;
    [SP + 28] = P0;
    [SP + 32] = P1;
    [SP + 36] = P2;
    [SP + 40] = R0;
    CC = R0 == 0;
    IF CC JUMP .Lactive_restore;
    R0 = 0;
    CALL sdk_sample_retry_owned;
    CC = R0 == 0;
    IF CC JUMP .Lactive_restore;
    R0 = 0;
    [SP + 40] = R0;
.Lactive_restore:
    R0 = [SP + 40];
    CC = R0 == 0;
    R0 = [SP + 12];
    R1 = [SP + 16];
    R2 = [SP + 20];
    R3 = [SP + 24];
    P0 = [SP + 28];
    P1 = [SP + 32];
    P2 = [SP + 36];
    P4.H = 0x0801;
    P4.L = 0xf7dc;
    UNLINK;
    RTS;
.size sdk_sample_active_retry, .-sdk_sample_active_retry

/* 8c0a21c0 replaces a literal load: R0 is the pending-path equality result
 * and CC is R0==0. A stale header completion retries the pending path, which
 * stock's duplicate check drops even with the worker idle. Keep busy
 * suppression; let an owned idle retry launch. Replay R5; keep every register. */
.global sdk_sample_pending_retry
.type sdk_sample_pending_retry, STT_FUNC
sdk_sample_pending_retry:
    LINK 44;
    [SP + 12] = R0;
    [SP + 16] = R1;
    [SP + 20] = R2;
    [SP + 24] = R3;
    [SP + 28] = P0;
    [SP + 32] = P1;
    [SP + 36] = P2;
    [SP + 40] = R0;
    CC = R0 == 0;
    IF CC JUMP .Lpending_restore;
    R0 = 1;
    CALL sdk_sample_retry_owned;
    CC = R0 == 0;
    IF CC JUMP .Lpending_restore;
    R0 = 0;
    [SP + 40] = R0;
.Lpending_restore:
    R0 = [SP + 40];
    CC = R0 == 0;
    R0 = [SP + 12];
    R1 = [SP + 16];
    R2 = [SP + 20];
    R3 = [SP + 24];
    P0 = [SP + 28];
    P1 = [SP + 32];
    P2 = [SP + 36];
    R5.H = 0x0801;
    R5.L = 0xf7c0;
    UNLINK;
    RTS;
.size sdk_sample_pending_retry, .-sdk_sample_pending_retry

/* R0=track, R1=raw key, R2=settings, stack: frames, last, canonical key. Calls stock
 * 8d588224(track, key, 60, 0, frames, frames, last) with the settings at
 * FP-8 and the return address sdk_sample_assign_owned_return, which is how
 * the fade hook below recognizes this call without shared state. */
.global sdk_sample_assign_owned
.type sdk_sample_assign_owned, STT_FUNC
sdk_sample_assign_owned:
    LINK 48;
    [SP + 40] = R2;
    R2 = [FP + 28];
    [SP + 36] = R2;
    R2 = [FP + 20];
    [SP + 16] = R2;
    [SP + 20] = R2;
    R2 = [FP + 24];
    [SP + 24] = R2;
    R2 = 0;
    [SP + 12] = R2;
    R2 = 60;
    P0 = 0x8d588224;
    CALL (P0);
.global sdk_sample_assign_owned_return
sdk_sample_assign_owned_return:
    UNLINK;
    RTS;
.size sdk_sample_assign_owned, .-sdk_sample_assign_owned

/* Only the fade conversion at 8d5882d8 is redirected here. Stock initializer
 * LINK 0 leaves its caller's return PC at [FP+4]. Recognizing our owned call
 * site scopes this override without shared state or changing other callers.
 * Its explicit inner-marker args skip the earlier 20%/80% conversions.
 */
.global sdk_sample_assign_fade
.type sdk_sample_assign_fade, STT_FUNC
sdk_sample_assign_fade:
    R1 = [FP + 4];
    R2.H = sdk_sample_assign_owned_return;
    R2.L = sdk_sample_assign_owned_return;
    CC = R1 == R2;
    IF !CC JUMP .Lassign_fade_stock;
    P0 = [FP];
    /* Stock writes R4 to the region key after this call. */
    R4 = [P0 - 12];
    R0 = [P0 - 8];
    RTS;
.Lassign_fade_stock:
    LINK 12;
    P0 = 0x04020fd8;
    CALL (P0);
    UNLINK;
    RTS;
.size sdk_sample_assign_fade, .-sdk_sample_assign_fade
