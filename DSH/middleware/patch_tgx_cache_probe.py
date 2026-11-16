#!/usr/bin/env python3
"""Add a D-cache-resident texture variant to the TGX benchmark.

Compares a 128x128 RGB565 texture (32 KB, exceeds the 16 KB D-cache) with a
64x64 one (8 KB, fits): if throughput jumps, the textured path is cache-bound,
otherwise it is ALU-bound.

Run from the project root:  python DSH/middleware/patch_tgx_cache_probe.py
"""
import io

PATH = "User/tgx_selftest.cpp"

ADD = r'''
static RGB565 s_tex64[64 * 64];         /* 8 KB: fits in the 16 KB D-cache */

static void make_texture64(void)
{
    for (int y = 0; y < 64; y++)
    {
        for (int x = 0; x < 64; x++)
        {
            s_tex64[y * 64 + x] = RGB565((x * 4) & 0xFF, (y * 4) & 0xFF,
                                         (((x ^ y) & 0x10) ? 0xE0 : 0x20));
        }
    }
}

/* same full-screen quad, but sampling an 8 KB texture */
static float bench_quad_small_tex(Image<RGB565> &dst, const Image<RGB565> &src, uint32_t reps)
{
    fVec2 s0(0, 0), s1(64, 0), s2(64, 64), s3(0, 64);
    fVec2 d0(0, 0), d1(SCR_W, 0), d2(SCR_W, SCR_H), d3(0, SCR_H);
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        dst.drawTexturedQuad(src, s0, s1, s2, s3, d0, d1, d2, d3, TGX_DEFAULT_NO_BLENDING);
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}
'''

src = io.open(PATH, encoding="utf-8").read()

if "bench_quad_small_tex" not in src:
    src = src.replace("/*--------------------------------------------------------------- demo screen */",
                      ADD.strip() + "\n\n/*--------------------------------------------------------------- demo screen */", 1)

old = """        printf("[TGX] 32/blend: %d.%02d Mpx/s\\r\\n", (int)r2, (int)(r2 * 100.0f) % 100);"""
new = old + """

        {
            Image<RGB565> small((RGB565 *)s_tex64, 64, 64);
            float r3;

            make_texture64();
            r3 = bench_quad_small_tex(dst, small, 4u);
            printf("[TGX] 565 8KB : %d.%02d Mpx/s  (texture fits in D-cache)\\r\\n",
                   (int)r3, (int)(r3 * 100.0f) % 100);
        }"""

if "565 8KB" not in src:
    src = src.replace(old, new, 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("cache probe added")
