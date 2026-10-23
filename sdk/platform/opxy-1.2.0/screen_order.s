/* Stock GUI compositor loop advance at 8d5208fa. R7 is the just-painted
 * logical page, P4 is its post-incremented slot cursor, [P5] the primary page.
 * Preserve every register except the original R0/R7/CC results and the cursor
 * P4. Stock's following IF CC performs the loop; page IDs are not renumbered.
 */
.section .text
.align 2
.extern sdk_screen_next
.global sdk_screen_advance
.type sdk_screen_advance, STT_FUNC
sdk_screen_advance:
    LINK 44;
    [SP + 12] = R1;
    [SP + 16] = R2;
    [SP + 20] = R3;
    [SP + 24] = P0;
    [SP + 28] = P1;
    [SP + 32] = P2;
    [SP + 36] = R7;
    R0 = R7;
    R1 = [P5];
    CALL sdk_screen_next;
    R1 = [SP + 36];
    R1 += 1;
    R1 = R0 - R1 (NS);
    R1 <<= 2;
    R2 = P4;
    R2 = R2 + R1 (NS);
    P4 = R2;
    R7 = R0;
    R1 = [SP + 12];
    R2 = [SP + 16];
    R3 = [SP + 20];
    P0 = [SP + 24];
    P1 = [SP + 28];
    P2 = [SP + 32];
    UNLINK;
    R0 = 128;
    CC = R7 < R0;
    RTS;
.size sdk_screen_advance, .-sdk_screen_advance
