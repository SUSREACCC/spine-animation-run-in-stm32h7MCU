#!/usr/bin/env python3
"""Extend tgx_selftest.cpp benchmarks with a texture-format / blending matrix.

Run from the project root:  python DSH/middleware/patch_tgx_matrix.py
"""
import io

PATH = "User/tgx_selftest.cpp"

NEW = r'''
/*--------------------------------------------------------------- matrix bench */
static RGB565 s_tex565[128 * 128];      /* 32 KB, no alpha */

static void make_texture565(void)
{
    for (int y = 0; y < 128; y++)
    {
        for (int x = 0; x < 128; x++)
        {
            s_tex565[y * 128 + x] = RGB565((x * 2) & 0xFF, (y * 2) & 0xFF,
                                           (((x ^ y) & 0x20) ? 0xE0 : 0x20));
        }
    }
}

static float bench_quad_generic(Image<RGB565> &dst, const Image<RGB32> &src32,
                                const Image<RGB565> &src565, int variant, uint32_t reps)
{
    fVec2 s0(0, 0), s1(128, 0), s2(128, 128), s3(0, 128);
    fVec2 d0(0, 0), d1(SCR_W, 0), d2(SCR_W, SCR_H), d3(0, SCR_H);
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        switch (variant)
        {
            case 0:   /* RGB565 source, overwrite */
                dst.drawTexturedQuad(src565, s0, s1, s2, s3, d0, d1, d2, d3, TGX_DEFAULT_NO_BLENDING);
                break;
            case 1:   /* RGB32 source, overwrite */
                dst.drawTexturedQuad(src32, s0, s1, s2, s3, d0, d1, d2, d3, TGX_DEFAULT_NO_BLENDING);
                break;
            default:  /* RGB32 source, alpha blend */
                dst.drawTexturedQuad(src32, s0, s1, s2, s3, d0, d1, d2, d3, 1.0f);
                break;
        }
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}
'''

src = io.open(PATH, encoding="utf-8").read()

if "bench_quad_generic" not in src:
    src = src.replace("/*--------------------------------------------------------------- demo screen */",
                      NEW.strip() + "\n\n/*--------------------------------------------------------------- demo screen */", 1)

# call the matrix from tgx_selftest()
old = """    printf("[TGX] tris   : %d.%02d Mpx/s  (16x12 grid, gradient triangles)\\r\\n",
           (int)tri_rate, (int)(tri_rate * 100.0f) % 100);"""

new = old + """

    {
        Image<RGB565> src565((RGB565 *)s_tex565, 128, 128);
        float r0, r1, r2;

        make_texture565();
        r0 = bench_quad_generic(dst, src, src565, 0, 4u);
        r1 = bench_quad_generic(dst, src, src565, 1, 4u);
        r2 = bench_quad_generic(dst, src, src565, 2, 4u);

        printf("[TGX] 565/ow : %d.%02d Mpx/s\\r\\n", (int)r0, (int)(r0 * 100.0f) % 100);
        printf("[TGX] 32/ow  : %d.%02d Mpx/s\\r\\n", (int)r1, (int)(r1 * 100.0f) % 100);
        printf("[TGX] 32/blend: %d.%02d Mpx/s\\r\\n", (int)r2, (int)(r2 * 100.0f) % 100);
    }"""

if "565/ow" not in src:
    src = src.replace(old, new, 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("benchmark matrix added")
