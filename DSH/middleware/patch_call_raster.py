#!/usr/bin/env python3
"""Wire the custom-rasterizer probe into the TGX self-test.

- includes raster_probe.h
- runs raster_probe() after the TGX benchmarks, before the demo screen
- shows the rasterizer number on the demo screen

Run from the project root:  python DSH/middleware/patch_call_raster.py
"""
import io

PATH = "User/tgx_selftest.cpp"

src = io.open(PATH, encoding="utf-8").read()

if "raster_probe.h" not in src:
    src = src.replace('#include "tgx_selftest.h"',
                      '#include "tgx_selftest.h"\n#include "raster_probe.h"', 1)

if "raster_probe();" not in src:
    old = "    draw_demo(dst, src, fill_rate, tex_rate, tri_rate);"
    new = ("    /* custom rasterizer prototype: same framebuffer, same load */\n"
           "    (void)raster_probe();\n\n"
           "    draw_demo(dst, src, fill_rate, tex_rate, tri_rate);")
    src = src.replace(old, new, 1)

if "RASTR:" not in src:
    old = """    sprintf(line, "framebuffer @ 0x%08lX  %dx%d RGB565", (unsigned long)FB_ADDR, SCR_W, SCR_H);
    lcd_show_string(20, 432, 780, 16, 16, line, 0x07FFu);"""
    new = """    sprintf(line, "framebuffer @ 0x%08lX  %dx%d RGB565", (unsigned long)FB_ADDR, SCR_W, SCR_H);
    lcd_show_string(20, 432, 780, 16, 16, line, 0x07FFu);

    if (g_raster_mpx > 0.0f)
    {
        sprintf(line, "RASTR: %d.%02d Mpx/s (custom raster, key+tint)",
                (int)g_raster_mpx, (int)(g_raster_mpx * 100.0f) % 100);
        lcd_show_string(20, 452, 780, 16, 16, line, 0xFFFFu);
    }"""
    src = src.replace(old, new, 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("tgx_selftest.cpp: raster probe wired in")
