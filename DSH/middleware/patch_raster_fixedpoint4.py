#!/usr/bin/env python3
"""Use float division for the edge slopes (VDIV is 14 cycles) but keep the
per-row stepping in 16.16 fixed point.

The previous attempt used int64 division, which compiles to __aeabi_ldivmod and
is far slower than VDIV.F32 on Cortex-M7 - measured 13.6 -> 14.0 ms.

Run from the project root:  python DSH/middleware/patch_raster_fixedpoint4.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

OLD = r'''            if (dy == 0)
            {
                e_step16[e] = 0;
                e_x16[e] = xa << 12;                       /* 4bit -> 16.16 像素 */
            }
            else
            {
                e_x16[e] = (int32_t)(((int64_t)xa << 12) +
                                     ((((int64_t)(yc0 - ya)) * (xb - xa)) << 12) / dy);
                e_step16[e] = (int32_t)((((int64_t)(xb - xa)) << 16) / dy);
            }'''

NEW = r'''            if (dy == 0)
            {
                e_step16[e] = 0;
                e_x16[e] = xa << 12;                       /* 4bit -> 16.16 像素 */
            }
            else
            {
                /* 斜率用一次浮点除法（VDIV 14 周期，远快于 int64 除法=库调用），
                 * 之后每行只做整数加法 */
                float slope = (float)(xb - xa) / (float)dy;    /* px / px */

                e_step16[e] = (int32_t)lrintf(slope * 65536.0f);
                e_x16[e] = (int32_t)lrintf(((float)xa + (float)(yc0 - ya) * slope) * 4096.0f);
            }'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "VDIV 14" in s:
        print("already patched")
        return

    if OLD not in s:
        raise SystemExit("int64 divide block not found")

    s = s.replace(OLD, NEW, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("edge slope: float divide + fixed stepping")


if __name__ == "__main__":
    main()
