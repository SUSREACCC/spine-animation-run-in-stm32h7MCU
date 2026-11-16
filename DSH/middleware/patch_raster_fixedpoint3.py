#!/usr/bin/env python3
"""Second half of the fixed-point triangle setup: edge x(y) intersections and
the per-row span derivation.

Slices between section markers:
  [三条边的 x(y)]..[UV / 颜色梯度]   -> 16.16 fixed-point edge stepping
  inside [逐行扫描]: the float intersection block -> integer min/max + shifts

Run from the project root:  python DSH/middleware/patch_raster_fixedpoint3.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

EDGE_START = "    /* ---------------- 三条边的 x(y) ---------------- */"
EDGE_END = "    /* ---------------- UV / 颜色梯度 ---------------- */"

NEW_EDGE = r'''    /* ---------------- 三条边的 x(y)：16.16 定点增量（无浮点、每行一次加法） ---------------- */
    int32_t e_x16[3];        /* 当前行的交点（16.16 像素） */
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
                e_x16[e] = (int32_t)(((int64_t)xa << 12) +
                                     ((((int64_t)(yc0 - ya)) * (xb - xa)) << 12) / dy);
                e_step16[e] = (int32_t)((((int64_t)(xb - xa)) << 16) / dy);
            }
        }
    }

'''

ROW_OLD_START = "        float fy = (float)y + 0.5f;"
ROW_OLD_END = "        if (xa < bx0) { xa = bx0; }"

NEW_ROW = r'''        int32_t yc = (y << SUBPIXEL_BITS) + (SUBPIXEL_ONE / 2);
        int32_t xa16 = 0x7FFFFFFF, xb16 = (int32_t)0x80000000;

        for (int e = 0; e < 3; e++)
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
        }

        /* 像素 i 的中心在 i+0.5：xa = ceil(x-0.5), xb = floor(x-0.5) */
        int xa = (xa16 + 0x7FFF) >> 16;
        int xb = (xb16 - 0x8000) >> 16;

'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "e_step16" in s:
        print("edge block already fixed-point")
    else:
        i = s.find(EDGE_START)
        j = s.find(EDGE_END)
        if (i < 0) or (j < 0):
            raise SystemExit("edge markers not found")
        s = s[:i] + NEW_EDGE + s[j:]

    i = s.find(ROW_OLD_START)
    j = s.find(ROW_OLD_END)

    if (i < 0) or (j < 0) or (j <= i):
        raise SystemExit("row markers not found")

    s = s[:i] + NEW_ROW + s[j:]

    # row 循环里已无 fy，UV/颜色改用 fyf
    s = s.replace("            float u = A->u + du_dx * (fx - A->x) + du_dy * (fy - A->y);",
                  "            float fyf = (float)y + 0.5f;\n            float u = A->u + du_dx * (fx - A->x) + du_dy * (fyf - A->y);")
    s = s.replace("            float v = A->v + dv_dx * (fx - A->x) + dv_dy * (fy - A->y);",
                  "            float v = A->v + dv_dx * (fx - A->x) + dv_dy * (fyf - A->y);")
    s = s.replace("                cr = (float)cr_c + dcrdx * (fx - A->x) + dcrdy * (fy - A->y);",
                  "                cr = (float)cr_c + dcrdx * (fx - A->x) + dcrdy * (fyf - A->y);")
    s = s.replace("                cg = (float)cg_c + dcgdx * (fx - A->x) + dcgdy * (fy - A->y);",
                  "                cg = (float)cg_c + dcgdx * (fx - A->x) + dcgdy * (fyf - A->y);")
    s = s.replace("                cb = (float)cb_c + dcbdx * (fx - A->x) + dcbdy * (fy - A->y);",
                  "                cb = (float)cb_c + dcbdx * (fx - A->x) + dcbdy * (fyf - A->y);")
    s = s.replace("                ca = (float)ca0 + da_dx * (fx - A->x) + da_dy * (fy - A->y);",
                  "                ca = (float)ca0 + da_dx * (fx - A->x) + da_dy * (fyf - A->y);")

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("edge/row blocks converted to fixed point")


if __name__ == "__main__":
    main()
