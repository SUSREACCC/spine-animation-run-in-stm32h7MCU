#!/usr/bin/env python3
"""Revert the per-row edge intersection to the proven float version, keeping the
fixed-point wins that are safe (bbox from fixed vertices, fixed-point winding).

The integer stepping produced stray horizontal dashes near moving parts: for
some triangles a scanline's x_right came out too large.  The float version had
no such artefact and costs the same (measured 13.60 vs 13.50 ms).

Run from the project root:  python DSH/middleware/patch_raster_revert_edge.py
"""
import io

CUR = "Middlewares/RASTER/raster2d.cpp"
BAK = "save/26-11-15-09-43/raster2d.cpp.before_fixedpoint"

EDGE_START = "    /* ---------------- 三条边的 x(y) ---------------- */"
EDGE_END = "    /* ---------------- UV / 颜色梯度 ---------------- */"

ROW_START = "        float fy = (float)y + 0.5f;"
ROW_END = "        if (xa < bx0) { xa = bx0; }"


def slice_between(text, start, end):
    i = text.find(start)
    j = text.find(end)
    if (i < 0) or (j < 0) or (j <= i):
        raise SystemExit("markers not found: %r .. %r" % (start[:30], end[:30]))
    return text[i:j]


def main():
    cur = io.open(CUR, encoding="utf-8").read()
    bak = io.open(BAK, encoding="utf-8").read()

    if "e_step16" not in cur:
        print("already reverted")
        return

    # 1) 边 x(y)：用备份里的浮点版本
    new_edge = slice_between(bak, EDGE_START, EDGE_END)
    cur = cur.replace(slice_between(cur, EDGE_START, EDGE_END), new_edge, 1)

    # 2) 行求交：备份里的浮点版本
    new_row = slice_between(bak, ROW_START, ROW_END)
    cur = cur.replace(slice_between(cur, ROW_START, ROW_END), new_row, 1)

    # 3) 行内 UV/颜色用的是 fyf（备份里是 fy），统一改回 fy
    cur = cur.replace("fyf", "fy")

    io.open(CUR, "w", encoding="utf-8", newline="").write(cur)
    print("edge intersection reverted to float; bbox/winding stay fixed-point")


if __name__ == "__main__":
    main()
