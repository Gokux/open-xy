/* Sample-analysis hooks that replace a load inside a stock function, so must
 * preserve volatile registers, and the memory barrier. The hooks that replace
 * stock calls, and the stock functions the cache uses, are in
 * sample_cache_stock.cpp. No hook is on the audio callback path.
 */
.section .text
.align 2
.extern extensions_sample_analysis_ready
.extern sdk_sample_cache_snapshot_keys
.extern sdk_sample_cache_tag_priority

.global sdk_sample_cache_barrier
.type sdk_sample_cache_barrier, STT_FUNC
sdk_sample_cache_barrier:
    SSYNC;
    RTS;
.size sdk_sample_cache_barrier, .-sdk_sample_cache_barrier

/* Gather completion: the stock track array is stable while its busy flag is
 * set. Replay the displaced old-sum load; ownership-only changes must also
 * enter stock desired-list rebuilding. R6 is the new stock path sum. */
.global sdk_sample_cache_snapshot
.type sdk_sample_cache_snapshot, STT_FUNC
sdk_sample_cache_snapshot:
    LINK 44;
    [SP + 20] = R1;
    [SP + 24] = R2;
    [SP + 28] = R3;
    [SP + 32] = P0;
    [SP + 36] = P1;
    [SP + 40] = P2;
    P0.H = 0x8403;
    P0.L = 0x64fc;
    R0 = [P0];
    [SP + 16] = R0;
    CALL extensions_sample_analysis_ready;
    CC = R0 == 1;
    IF !CC JUMP .Lsnapshot_stock;
    R0 = R6;
    R1 = [SP + 16];
    R2.H = 0x842a;
    R2.L = 0x3c2c;
    P0.H = 0x842a;
    P0.L = 0x402c;
    R3 = [P0];
    /* Stock auditions replace the current region while its browser is open.
     * Only this GUI-role capture may consult the current screen. Publish an
     * empty request set during browsing; the stock leave callback marks the
     * desired list dirty, so closing republishes the final assignment even
     * when the path checksum is unchanged. Existing ready cache stays valid.
     */
    P0.H = 0x8400;
    P0.L = 0x8c64;
    R0 = [P0];
    R1 = 4;
    CC = R0 == R1;
    IF !CC JUMP .Lsnapshot_capture;
    R2 = 0;
    R3 = 0;
.Lsnapshot_capture:
    R0 = R6;
    R1 = [SP + 16];
    [SP + 12] = R3;
    CALL sdk_sample_cache_snapshot_keys;
    JUMP .Lsnapshot_done;
.Lsnapshot_stock:
    R0 = [SP + 16];
.Lsnapshot_done:
    R1 = [SP + 20];
    R2 = [SP + 24];
    R3 = [SP + 28];
    P0 = [SP + 32];
    P1 = [SP + 36];
    P2 = [SP + 40];
    UNLINK;
    RTS;
.size sdk_sample_cache_snapshot, .-sdk_sample_cache_snapshot

/* Only the IPC copy carries bit 7; stock priorities remain unchanged. The
 * stock producers use 0/1/5/6/10/11/15/16 for regions and 0/99 for previews.
 * This replaces a load inside message construction, so preserve all volatile
 * argument/pointer registers, CC and the ordinary callee-saved registers. */
.global sdk_sample_cache_ipc_priority
.type sdk_sample_cache_ipc_priority, STT_FUNC
sdk_sample_cache_ipc_priority:
    LINK 48;
    [SP + 16] = R1;
    [SP + 20] = R2;
    [SP + 24] = R3;
    [SP + 28] = P0;
    [SP + 32] = P1;
    [SP + 36] = P2;
    /* Stock branches on CC at 8d4d95a8, after this load: keep it. */
    R0 = CC;
    [SP + 44] = R0;
    R0 = B[P5 + 100] (Z);
    [SP + 40] = R0;
    CALL extensions_sample_analysis_ready;
    CC = R0 == 1;
    IF !CC JUMP .Lpriority_stock;
    R0 = [P5 + 96];
    R1 = [SP + 40];
    CALL sdk_sample_cache_tag_priority;
    JUMP .Lpriority_done;
.Lpriority_stock:
    R0 = [SP + 40];
.Lpriority_done:
    [SP + 40] = R0;
    R0 = [SP + 44];
    CC = R0;
    R0 = [SP + 40];
    R1 = [SP + 16];
    R2 = [SP + 20];
    R3 = [SP + 24];
    P0 = [SP + 28];
    P1 = [SP + 32];
    P2 = [SP + 36];
    UNLINK;
    RTS;
.size sdk_sample_cache_ipc_priority, .-sdk_sample_cache_ipc_priority

