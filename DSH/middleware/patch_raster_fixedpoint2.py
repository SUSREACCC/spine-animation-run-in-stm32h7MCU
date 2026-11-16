#!/usr/bin/env python3
"""Replace the float triangle setup in raster_tri() with fixed-point code.

Uses index slicing between two section markers instead of exact-string matching,
because the surrounding code has been patched several times.

Run from the project root:  python DSH/middleware/patch_raster_fixedpoint2.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

START = "    /* ---------------- 包围盒 ---------------- */"
END = "    /* ---------------- 边增量 ---------------- */"

NEW_SETUP = r'''    /* ---------------- 顶点定点化（clamp 后用定点，不再回浮点） ---------------- */
    int32_t AX0, AY0, AX1, AY1, AX2, AY2;
    {
        const raster_vertex_t *V[3] = { A, B, C };
        int32_t *px[3] = { &AX0, &AX1, &AX2 };
        int32_t *py[3] = { &AY0, &AY1, &AY2 };

        for (int i = 0; i < 3; i++)
        {
            float fx = V[i]->x, fy = V[i]->y;

            if (fx < -COORD_CLAMP) { fx = -COORD_CLAMP; } else if (fx > COORD_CLAMP) { fx = COORD_CLAMP; }
            if (fy < -COORD_CLAMP) { fy = -COORD_CLAMP; } else if (fy > COORD_CLAMP) { fy = COORD_CLAMP; }

            *px[i] = (int32_t)lrintf(fx * SUBPIXEL_ONE);
            *py[i] = (int32_t)lrintf(fy * SUBPIXEL_ONE);
        }
    }

    /* ---------------- 绕序统一（纯定点） ---------------- */
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

    /* ---------------- 包围盒：由定点顶点直接取整（省掉浮点 min/max + 转换） ---------------- */
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

        bx0 = minX >> SUBPIXEL_BITS;                            /* floor */
        bx1 = (maxX + (SUBPIXEL_ONE - 1)) >> SUBPIXEL_BITS;     /* ceil  */
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

    if "AX0 = (int32_t)lrintf" in s or "int32_t AX0, AY0" in s:
        print("already patched")
        return

    i = s.find(START)
    j = s.find(END)

    if (i < 0) or (j < 0) or (j <= i):
        raise SystemExit("markers not found")

    s = s[:i] + NEW_SETUP + s[j:]

    # 边增量块里引用 X0..Y2，改成引用 AX0..AY2
    s = s.replace("    const int32_t X0 = AX0, Y0 = AY0, X1 = AX1, Y1 = AY1, X2 = AX2, Y2 = AY2;\n", "")
    for a, b in (("X0", "AX0"), ("Y0", "AY0"), ("X1", "AX1"), ("Y1", "AY1"), ("X2", "AX2"), ("Y2", "AY2")):
        # 只在该函数内替换（此时文件里 X0.. 只出现在这个函数）
        s = s.replace("(X1 - X0)", "(AX1 - AX0)").replace("(X2 - X0)", "(AX2 - AX0)")
        s = s.replace("(Y2 - Y0)", "(AY2 - AY0)").replace("(Y1 - Y0)", "(AY1 - AY0)")
        s = s.replace("(Y2 - Y1)", "(AY2 - AY1)").replace("(X2 - X1)", "(AX2 - AX1)")
        s = s.replace("(Y0 - Y2)", "(AY0 - AY2)").replace("(X0 - X2)", "(AX0 - AX2)")

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("setup replaced (marker slicing)")


if __name__ == "__main__":
    main()
