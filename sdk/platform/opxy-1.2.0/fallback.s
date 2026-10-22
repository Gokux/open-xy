/* A curated startup includes every available machine. When a machine is not
 * selected, only its startup callbacks resolve here; its code/state is omitted.
 * Never use these fallbacks for imports from an included machine. */
.section .text
.align 2
.global kit_absent
.type kit_absent, STT_FUNC
kit_absent:
    R0 = 0;
    RTS;
.size kit_absent, .-kit_absent

/* The first catalog adapter is also the stock delegation path. Preserve the
 * missing-engine sentinel check when that first machine is not selected. */
.global kit_catalog_stock
.type kit_catalog_stock, STT_FUNC
kit_catalog_stock:
    R3 = 33;
    CC = R2 == R3;
    IF CC JUMP .Lmissing;
    JUMP.L stock_catalog_insert;
.Lmissing:
    R0 = 0;
    RTS;
.size kit_catalog_stock, .-kit_catalog_stock
