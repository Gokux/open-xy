/* Drum-page encoder press entry. The other encoder hooks are C++ in
 * sample_controls_stock.cpp. */
.section .text
.align 2
.extern sdk_sample_press_engine_owned

/* 8c0b3290 replaces a CALL with R0 = track; the caller keeps the button index
 * minus six (4..7) in R5, which C++ cannot read. Pass it as the second argument. */
.global sdk_sample_press_engine
.type sdk_sample_press_engine, STT_FUNC
sdk_sample_press_engine:
    R1 = R5;
    JUMP.L sdk_sample_press_engine_owned;
.size sdk_sample_press_engine, .-sdk_sample_press_engine
