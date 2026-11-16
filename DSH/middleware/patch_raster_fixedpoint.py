#!/usr/bin/env python3
"""Replace the float triangle setup in raster_tri() with fixed-point code.

Before: bbox from float min/max, six lrintf conversions, three float divisions
        for the edge slopes, and a float multiply per edge per row.
After:  bbox derived directly from the 4-bit fixed vertices, edge x(y) steered
        with 16.16 fixed increments (one integer division per edge, done once).

The endpoint validation with the integer edge functions is kept, so the
top-left rule (and therefore the T1/T2 regressions) remain exact.

Run from the project root:  python DSH/middleware/patch_raster_fixedpoint.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

OLD = r'''    /* ---------------- 包围盒 ---------------- */
    float minx = A->x < B->x ? (A->x < C->x ? A->x : C->x) : (B->x < C->x ? B->x : C->x);
    float maxx = A->x > B->x ? (A->x > C->x ? A->x : C->x) : (B->x > C->x ? B->x : C->x);
    float miny = A->y < B->y ? (A->y < C->y ? A->y : C->y) : (B->y < C->y ? B->y : C->y);
    float maxy = A->y > B->y ? (A->y > C->y ? A->y : C->y) : (B->y > C->y ? B->y : C->y);

    int bx0 = (int)floorf(minx), bx1 = (int)ceilf(maxx);
    int by0 = (int)floorf(miny), by1 = (int)ceilf(maxy);

    if (bx0 < s->clip_x0) { bx0 = s->clip_x0; }
    if (by0 < s->clip_y0) { by0 = s->clip_y0; }
    if (bx1 > s->clip_x1) { bx1 = s->clip_x1; }
    if (by1 > s->clip_y1) { by1 = s->clip_y1; }
    if ((bx0 > bx1) || (by0 > by1))
    {
        return;
    }
'''

NEW = r'''    /* ---------------- 顶点定点化（clamp 保证 int32 安全） ---------------- */
    {
        float fx = A->x, fy = A->y;

        if (fx < -COORD_CLAMP) { fx = -COORD_CLAMP; } else if (fx > COORD_CLAMP) { fx = COORD_CLAMP; }
        if (fy < -COORD_CLAMP) { fy = -COORD_CLAMP; } else if (fy > COORD_CLAMP) { fy = COORD_CLAMP; }
        AX0 = (int32_t)lrintf(fx * SUBPIXEL_ONE);
        AY0 = (int32_t)lrintf(fy * SUBPIXEL_ONE);

        fx = B->x; fy = B->y;
        if (fx < -COORD_CLAMP) { fx = -COORD_CLAMP; } else if (fx > COORD_CLAMP) { fx = COORD_CLAMP; }
        if (fy < -COORD_CLAMP) { fy = -COORD_CLAMP; } else if (fy > COORD_CLAMP) { fy = COORD_CLAMP; }
        AX1 = (int32_t)lrintf(fx * SUBPIXEL_ONE);
        AY1 = (int32_t)lrintf(fy * SUBPIXEL_ONE);

        fx = C->x; fy = C->y;
        if (fx < -COORD_CLAMP) { fx = -COORD_CLAMP; } else if (fx > COORD_CLAMP) { fx = COORD_CLAMP; }
        if (fy < -COORD_CLAMP) { fy = -COORD_CLAMP; } else if (fy > COORD_CLAMP) { fy = COORD_CLAMP; }
        AX2 = (int32_t)lrintf(fx * SUBPIXEL_ONE);
        AY2 = (int32_t)lrintf(fy * SUBPIXEL_ONE);
    }

    /* ---------------- 绕序统一（定点，不再动浮点副本） ---------------- */
    {
        int32_t area = (AX1 - AX0) * (AY2 - AY0) - (AX2 - AX0) * (AY1 - AY0);

        if (area == 0)
        {
            return;
        }
        if (area < 0)
        {
            int32_t ti = AX1; AX1 = AX2; AX2 = ti;
            ti = AY1; AY1 = AY2; AY2 = ti;
            const raster_vertex_t *tv = B; B = C; C = tv;
        }
    }

    /* ---------------- 包围盒：直接由定点顶点取整 ---------------- */
    int bx0, bx1, by0, by1;
    {
        int32_t minX = AX0, maxX = AX0, minY = AY0, maxY = AY0;

        if (AX1 < minX) { minX = AX1; }
        if (AX1 > maxX) { maxX = AX1; }
        if (AX2 < minX) { minX = AX2; }
        if (AX2 > maxX) { maxX = AX2; }
        if (AY1 < minY) { minY = AY1; }
        if (AY1 > maxY) { maxY = AY1; }
        if (AY2 < minY) { minY = AY2; }
        if (AY2 > maxY) { maxY = AY2; }

        bx0 = minX >> SUBPIXEL_BITS;                                  /* floor */
        bx1 = (maxX + (SUBPIXEL_ONE - 1)) >> SUBPIXEL_BITS;           /* ceil  */
        by0 = minY >> SUBPIXEL_BITS;
        by1 = (maxY + (SUBPIXEL_ONE - 1)) >> SUBPIXEL_BITS;
    }

    if (bx0 < s->clip_x0) { bx0 = s->clip_x0; }
    if (by0 < s->clip_y0) { by0 = s->clip_y0; }
    if (bx1 > s->clip_x1) { bx1 = s->clip_x1; }
    if (by1 > s->clip_y1) { by1 = s->clip_y1; }
    if ((bx0 > bx1) || (by0 > by1))
    {
        return;
    }
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "AX0 = (int32_t)lrintf" in s:
        print("already patched")
        return

    if OLD not in s:
        raise SystemExit("bbox block not found")

    s = s.replace(OLD, NEW, 1)

    # 旧的定点化/绕序块现在要删掉（已经被合并进上面的新块）
    old_fix = r'''    /* ---------------- 定点化 ---------------- */
    float ax = A->x, ay = A->y, bx = B->x, by = B->y, cx = C->x, cy = C->y;

    if (ax < -COORD_CLAMP) { ax = -COORD_CLAMP; } else if (ax > COORD_CLAMP) { ax = COORD_CLAMP; }
    if (ay < -COORD_CLAMP) { ay = -COORD_CLAMP; } else if (ay > COORD_CLAMP) { ay = COORD_CLAMP; }
    if (bx < -COORD_CLAMP) { bx = -COORD_CLAMP; } else if (bx > COORD_CLAMP) { bx = COORD_CLAMP; }
    if (by < -COORD_CLAMP) { by = -COORD_CLAMP; } else if (by > COORD_CLAMP) { by = COORD_CLAMP; }
    if (cx < -COORD_CLAMP) { cx = -COORD_CLAMP; } else if (cx > COORD_CLAMP) { cx = COORD_CLAMP; }
    if (cy < -COORD_CLAMP) { cy = -COORD_CLAMP; } else if (cy > COORD_CLAMP) { cy = COORD_CLAMP; }

    int32_t X0 = (int32_t)lrintf(ax * SUBPIXEL_ONE), Y0 = (int32_t)lrintf(ay * SUBPIXEL_ONE);
    int32_t X1 = (int32_t)lrintf(bx * SUBPIXEL_ONE), Y1 = (int32_t)lrintf(by * SUBPIXEL_ONE);
    int32_t X2 = (int32_t)lrintf(cx * SUBPIXEL_ONE), Y2 = (int32_t)lrintf(cy * SUBPIXEL_ONE);

    int32_t area = (X1 - X0) * (Y2 - Y0) - (X2 - X0) * (Y1 - Y0);

    if (area == 0)
    {
        return;
    }
    if (area < 0)
    {
        int32_t ti = X1; X1 = X2; X2 = ti;
        ti = Y1; Y1 = Y2; Y2 = ti;
        const raster_vertex_t *tv = B; B = C; C = tv;
        float tf;
        tf = bx; bx = cx; cx = tf;
        tf = by; by = cy; cy = tf;
    }

    /* ---------------- 边增量 ---------------- */
'''
    new_fix = r'''    /* ---------------- 边增量 ---------------- */
    const int32_t X0 = AX0, Y0 = AY0, X1 = AX1, Y1 = AY1, X2 = AX2, Y2 = AY2;
'''
    if old_fix not in s:
        raise SystemExit("fixed-point block not found")
    s = s.replace(old_fix, new_fix, 1)

    # 函数开头声明 AX0..AY2
    head = r'''    const raster_vertex_t *B = B0, *C = C0;
'''
    head_new = r'''    const raster_vertex_t *B = B0, *C = C0;

    int32_t AX0, AY0, AX1, AY1, AX2, AY2;
'''
    if head not in s:
        raise SystemExit("function head not found")
    s = s.replace(head, head_new, 1)

    # 边的 x(y)：浮点 -> 16.16 定点
    old_edge = r'''    /* ---------------- 三条边的 x(y)（浮点，用于求每行区间） ---------------- */
    float vx[3] = { ax, bx, cx };
    float vy[3] = { ay, by, cy };
    float ex_int[3], ey_lo[3], ey_hi[3], e_slope[3];

    for (int e = 0; e < 3; e++)
    {
        int a = e, b = (e + 1) % 3;
        float ya = vy[a], yb = vy[b];
        float xa = vx[a], xb = vx[b];

        ey_lo[e] = ya < yb ? ya : yb;
        ey_hi[e] = ya < yb ? yb : ya;

        float dy = yb - ya;

        if (fabsf(dy) < 0.0001f)
        {
            e_slope[e] = 0.0f;
            ex_int[e] = xa;
        }
        else
        {
            e_slope[e] = (xb - xa) / dy;
            ex_int[e] = xa - ya * e_slope[e];
        }
    }
'''
    new_edge = r'''    /* ---------------- 三条边的 x(y)：16.16 定点增量 ---------------- */
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
                /* x16(行首) = xa<<12 + ((yc0-ya)*dx<<12)/dy ; 每行 +16*dx/dy<<12 */
                int64_t num = ((int64_t)(yc0 - ya) * (xb - xa)) << 12;
                int64_t step = ((int64_t)(xb - xa)) << 16;

                e_x16[e] = (int32_t)(((int64_t)xa << 12) + num / dy);
                e_step16[e] = (int32_t)(step / dy);
            }
        }
    }
'''
    if old_edge not in s:
        raise SystemExit("edge x(y) block not found")
    s = s.replace(old_edge, new_edge, 1)

    # 行循环里的求交
    old_row = r'''        float fy = (float)y + 0.5f;
        float xa_f = 1e9f, xb_f = -1e9f;

        for (int e = 0; e < 3; e++)
        {
            if ((fy < ey_lo[e]) || (fy > ey_hi[e]))
            {
                continue;
            }

            float xe = ex_int[e] + fy * e_slope[e];

            if (xe < xa_f) { xa_f = xe; }
            if (xe > xb_f) { xb_f = xe; }
        }

        int xa = (int)ceilf(xa_f - 0.5f);
        int xb = (int)floorf(xb_f - 0.5f);
'''
    new_row = r'''        int32_t yc = (y << SUBPIXEL_BITS) + (SUBPIXEL_ONE / 2);
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
    if old_row not in s:
        raise SystemExit("row intersection block not found")
    s = s.replace(old_row, new_row, 1)

    # 行首 UV/颜色用 fy，现在没有 fy 了，改回 float
    old_uv = "            float fx = (float)xa + 0.5f;\n            float u = A->u + du_dx * (fx - A->x) + du_dy * (fy - A->y);"
    new_uv = "            float fx = (float)xa + 0.5f;\n            float fyf = (float)y + 0.5f;\n            float u = A->u + du_dx * (fx - A->x) + du_dy * (fyf - A->y);"
    if old_uv not in s:
        raise SystemExit("uv block not found")
    s = s.replace(old_uv, new_uv, 1)
    s = s.replace("float v = A->v + dv_dx * (fx - A->x) + dv_dy * (fy - A->y);",
                  "float v = A->v + dv_dx * (fx - A->x) + dv_dy * (fyf - A->y);")
    s = s.replace("cr = (float)cr_c + dcrdx * (fx - A->x) + dcrdy * (fy - A->y);",
                  "cr = (float)cr_c + dcrdx * (fx - A->x) + dcrdy * (fyf - A->y);")
    s = s.replace("cg = (float)cg_c + dcgdx * (fx - A->x) + dcgdy * (fy - A->y);",
                  "cg = (float)cg_c + dcgdx * (fx - A->x) + dcgdy * (fyf - A->y);")
    s = s.replace("cb = (float)cb_c + dcbdx * (fx - A->x) + dcbdy * (fy - A->y);",
                  "cb = (float)cb_c + dcbdx * (fx - A->x) + dcbdy * (fyf - A->y);")
    s = s.replace("ca = (float)ca0 + da_dx * (fx - A->x) + da_dy * (fy - A->y);",
                  "ca = (float)ca0 + da_dx * (fx - A->x) + da_dy * (fyf - A->y);")

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("fixed-point triangle setup installed")


if __name__ == "__main__":
    main()
