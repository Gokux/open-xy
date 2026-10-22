/* Drum-page fade hook: it replaces instructions inside a stock function, so
 * it must preserve every register and CC. The rest of the drum page is C++ in
 * sample_drum_stock.cpp. */
.section .text
.align 2
.extern sdk_sample_drum_owned

/* 8d5349e4 replaces R0=[P1+20]; R0>>>=8. Preserve all other live
 * registers and CC; stock/absent/conflicting registrations replay exactly.
 */
.global sdk_sample_drum_fade
.type sdk_sample_drum_fade, STT_FUNC
sdk_sample_drum_fade:
    LINK 44;
    [SP + 16] = R1;
    [SP + 20] = R2;
    [SP + 24] = R3;
    [SP + 28] = P0;
    [SP + 32] = P1;
    [SP + 36] = P2;
    R0 = CC;
    [SP + 40] = R0;
    R0 = [P1 + 20];
    R0 >>>= 8;
    [SP + 12] = R0;
    CALL sdk_sample_drum_owned;
    CC = R0 == 1;
    IF !CC JUMP .Ldrum_fade_restore;
    R0 = 0;
    [SP + 12] = R0;
.Ldrum_fade_restore:
    R0 = [SP + 40];
    CC = R0;
    R1 = [SP + 16];
    R2 = [SP + 20];
    R3 = [SP + 24];
    P0 = [SP + 28];
    P1 = [SP + 32];
    P2 = [SP + 36];
    R0 = [SP + 12];
    UNLINK;
    RTS;
.size sdk_sample_drum_fade, .-sdk_sample_drum_fade
