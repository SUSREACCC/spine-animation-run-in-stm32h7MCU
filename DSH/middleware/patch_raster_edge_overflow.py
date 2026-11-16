#!/usr/bin/env python3
"""Fix int32 overflow in the fixed-point edge stepping.

Near-horizontal triangle edges (|dy| < 1 px) produce slopes in the tens of
thousands; slope * 65536 overflows int32 and wraps, which made a scanline span
run across the whole screen (the horizontal stray lines).

Fix:
  * compute the edge's x at ITS OWN first row (e_ylo), where the value is bounded
    by |dx|, instead of at the triangle's first row;
  * start stepping only when the row enters that edge's y-range;
  * clamp the per-row step (an edge taller than 0 but shorter than a pixel never
    steps anyway).

Run from the project root:  python DSH/middleware/patch_raster_edge_overflow.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

OLD_SETUP = r'''    int32_t e_x16[3];        /* 当前行的交点（16.16 像素） */
    int32_t e_step16[3];     /* 每行增量（16.16 像素）    */
    int32_t e_ylo[3], e_yhi[3];

    {
        const int32_t VX[3] = { AX0, AX1, AX2 };
        const int32_t VY[3] = { AY0, AY1, AY2 };
        const int32_t yc0 = (by0 << SUBPIXEL_BITS) + (SUBPIXEL_ONE / 2);

        for (int e = 0; e < 3; e++)
        {
            int32_t a = e, b = (e + 1) % 3;
            int32_t xa = VX[a], ya = VY[a], xb = VX[b], yb = VY[b];

            e_ylo[e] = ya < yb ? ya : yb;
            e_yhi[e] = ya < yb ? yb : ya;

            int32_t dy = yb - ya;

            if (dy == 0)
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
            }
        }
    }'''

NEW_SETUP = r'''    int32_t e_x16[3];        /* 当前行的交点（16.16 像素） */
    int32_t e_xstart16[3];   /* 该边第一行（e_ylo）上的交点，保证有界 */
    int32_t e_step16[3];     /* 每行增量（16.16 像素）    */
    int32_t e_ylo[3], e_yhi[3];
    bool    e_started[3];

    {
        const int32_t VX[3] = { AX0, AX1, AX2 };
        const int32_t VY[3] = { AY0, AY1, AY2 };

        for (int e = 0; e < 3; e++)
        {
            int32_t a = e, b = (e + 1) % 3;
            int32_t xa = VX[a], ya = VY[a], xb = VX[b], yb = VY[b];

            e_ylo[e] = ya < yb ? ya : yb;
            e_yhi[e] = ya < yb ? yb : ya;
            e_x16[e] = 0;
            e_started[e] = false;

            int32_t dy = yb - ya;

            if (dy == 0)
            {
                e_step16[e] = 0;
                e_xstart16[e] = xa << 12;                  /* 4bit -> 16.16 像素 */
            }
            else
            {
                /* 斜率用一次浮点除法（VDIV 14 周期，远快于 int64 除法=库调用）。
                 * x 只在"该边自己的起始行"上取初值：(e_ylo - ya) ∈ [0, dy]，
                 * 因此 (xa + (e_ylo-ya)*slope) 必然有界（≤ |dx|），不会溢出。 */
                float slope = (float)(xb - xa) / (float)dy;

                float stepf = slope * 65536.0f;

                /* 高度不足 1 像素的边跨不过一行，直接置 0，避免 int32 回绕 */
                if ((stepf > 2.0e9f) || (stepf < -2.0e9f))
                {
                    stepf = 0.0f;
                }
                e_step16[e] = (int32_t)lrintf(stepf);
                e_xstart16[e] = (int32_t)lrintf(((float)xa + (float)(e_ylo[e] - ya) * slope) * 4096.0f);
            }
        }
    }'''

OLD_ROW = r'''        for (int e = 0; e < 3; e++)
        {
            if ((yc < e_ylo[e]) || (yc > e_yhi[e]))
            {
                e_x16[e] += e_step16[e];
                continue;
            }

            int32_t xe = e_x16[e];

            if (xe < xa16) { xa16 = xe; }
            if (xe > xb16) { xb16 = xe; }

            e_x16[e] = xe + e_step16[e];
        }'''

NEW_ROW = r'''        for (int e = 0; e < 3; e++)
        {
            if ((yc < e_ylo[e]) || (yc > e_yhi[e]))
            {
                continue;                                  /* 该边在这一行不参与 */
            }

            if (!e_started[e])
            {
                /* 首次进入该边的 y 范围：从 e_ylo 上的有界初值起算 */
                e_x16[e] = e_xstart16[e] + (yc - e_ylo[e]) * e_step16[e];
                e_started[e] = true;
            }

            int32_t xe = e_x16[e];

            if (xe < xa16) { xa16 = xe; }
            if (xe > xb16) { xb16 = xe; }

            e_x16[e] = xe + e_step16[e];
        }'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "e_xstart16" in s:
        print("already patched")
        return

    if OLD_SETUP not in s:
        raise SystemExit("edge setup block not found")
    s = s.replace(OLD_SETUP, NEW_SETUP, 1)

    if OLD_ROW not in s:
        raise SystemExit("row block not found")
    s = s.replace(OLD_ROW, NEW_ROW, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("edge overflow fixed (bounded start + lazy stepping)")


if __name__ == "__main__":
    main()
