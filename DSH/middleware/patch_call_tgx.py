#!/usr/bin/env python3
"""Wire the TGX 2D self-test into User/selftest.c (keeps the existing 5-item boot test).

Flow becomes:  5 driver/FatFs tests -> summary screen -> 1.5 s -> TGX 2D demo+bench -> heartbeat

Run from the project root:  python DSH/middleware/patch_call_tgx.py
"""
import io

PATH = "User/selftest.c"

src = io.open(PATH, encoding="utf-8").read()

# 1) include + result variable
if "tgx_selftest.h" not in src:
    src = src.replace('#include "selftest.h"', '#include "tgx_selftest.h"\n#include "selftest.h"', 1)

if "g_rc_tgx" not in src:
    src = src.replace("static uint8_t  g_rc_ffs   = ST_PENDING;",
                      "static uint8_t  g_rc_ffs   = ST_PENDING;\nstatic uint8_t  g_rc_tgx   = ST_PENDING;", 1)

# 2) run the TGX test after the summary screen, before the heartbeat loop
old = """    printf("----------------------------------------------\\r\\n");
    printf("heartbeat start\\r\\n");"""

new = """    printf("----------------------------------------------\\r\\n");

    /* ---- TGX 2D render self-test + throughput benchmark (keeps boot test above) ---- */
    delay_ms(1500);
    printf("[TGX] starting 2D render test\\r\\n");
    g_rc_tgx = tgx_selftest();
    printf("RESULT TGX=%s\\r\\n", rc_str(g_rc_tgx));
    printf("----------------------------------------------\\r\\n");

    printf("heartbeat start\\r\\n");"""

if "[TGX] starting" not in src:
    src = src.replace(old, new, 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("selftest.c: TGX step wired in")
