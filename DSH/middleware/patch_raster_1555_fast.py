#!/usr/bin/env python3
"""Optimise the ARGB1555 fast path in raster2d.cpp.

1. ARGB1555 + constant colour + normal blend + opaque + white tint  -> the common
   spine case: convert 1555 to 565 with pure bit shuffling (no 8-bit round trip).
2. ARGB1555 + constant colour + opaque (tinted) -> tint in 5-5-5 space.

Both are selected by loop-invariant predicates so the per-pixel branch is
perfectly predictable.

Run from the project root:  python DSH/middleware/patch_raster_1555_fast.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

PROLOGUE_ANCHOR = "    TexCfg tex = make_texcfg(t);"

PROLOGUE_NEW = """    TexCfg tex = make_texcfg(t);

    /* ---- 1555 快路径的循环不变前置计算 ---- */
    const bool white_tint = (cr_c == 255) && (cg_c == 255) && (cb_c == 255) &&
                            (((A->color >> 24) & 0xFF) == 255);
    const int  t5r = (cr_c * 32 + 127) / 255;      /* 0..32 */
    const int  t5g = (cg_c * 32 + 127) / 255;
    const int  t5b = (cb_c * 32 + 127) / 255;
"""

FAST_BLOCK = r'''
                uint16_t texel = tex.px[tv * tex.stride + tu];

                /* ---- ARGB1555 + 常量色 + Normal：在 565/555 空间直接出结果 ---- */
                if constexpr ((FMT == 1) && (COLMODE == 0) && (BLEND == 0))
                {
                    if (white_tint && (opacity >= 255u))
                    {
                        /* 纯位重组：1555 -> 565（绿通道 5->6 位补一位） */
                        if ((texel & 0x8000u) != 0u)
                        {
                            row[x] = (uint16_t)((((texel >> 10) & 0x1F) << 11) |
                                                ((((texel >> 5) & 0x1F) << 1) << 5) |
                                                (texel & 0x1F));
                        }
                    }
                    else if ((texel & 0x8000u) != 0u)
                    {
                        int r5 = (texel >> 10) & 0x1F;
                        int g5 = (texel >> 5) & 0x1F;
                        int b5 = texel & 0x1F;

                        r5 = (r5 * t5r + 16) >> 5;
                        g5 = (g5 * t5g + 16) >> 5;
                        b5 = (b5 * t5b + 16) >> 5;

                        uint16_t s565 = (uint16_t)((r5 << 11) | (g5 << 6) | b5);

                        int ta = mul255(opacity, (A->color >> 24) & 0xFF);

                        row[x] = (ta >= 255) ? s565 : lerp565(row[x], s565, ta);
                    }
                }
                else
                {
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "1555 快路径" in s:
        print("already patched")
        return

    if PROLOGUE_ANCHOR not in s:
        raise SystemExit("prologue anchor not found")
    s = s.replace(PROLOGUE_ANCHOR, PROLOGUE_NEW.rstrip(), 1)

    old_fetch = "                uint16_t texel = tex.px[tv * tex.stride + tu];"
    if old_fetch not in s:
        raise SystemExit("texel anchor not found")
    s = s.replace(old_fetch, FAST_BLOCK.rstrip(), 1)

    # close the new else-block right before the inner loop's stepping lines
    old_tail = """                u += du_dx;
                v += dv_dx;"""
    new_tail = """                }   /* end of general 8-bit path */

                u += du_dx;
                v += dv_dx;"""
    if old_tail not in s:
        raise SystemExit("tail anchor not found")
    s = s.replace(old_tail, new_tail, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("ARGB1555 fast paths installed")


if __name__ == "__main__":
    main()
