/* Diagnostic callback stopwatch. Unsigned subtraction handles one 32-bit wrap. */
.section .text
.align 2
.global sdk_benchmark_cycles
.type sdk_benchmark_cycles, STT_FUNC
sdk_benchmark_cycles:
    R0 = CYCLES;
    RTS;
.size sdk_benchmark_cycles, .-sdk_benchmark_cycles

/* The synth voice adapter's clock: the 64-bit cycle count in 2^17-cycle ticks
   (about 0.33 ms at 400 MHz), wrapping after some 16 days. Reading CYCLES
   latches CYCLES2. */
.global sdk_voice_ticks
.type sdk_voice_ticks, STT_FUNC
sdk_voice_ticks:
    R0 = CYCLES;
    R1 = CYCLES2;
    R0 >>= 17;
    R1 <<= 15;
    R0 = R0 | R1;
    RTS;
.size sdk_voice_ticks, .-sdk_voice_ticks
