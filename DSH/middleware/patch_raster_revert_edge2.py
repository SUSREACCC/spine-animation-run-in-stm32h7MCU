#!/usr/bin/env python3
"""Revert the per-row edge intersection to the proven float version, keeping the
safe fixed-point parts (bbox from fixed vertices, fixed-point winding).

Locates the blocks by substring and snaps to line starts, so it tolerates the
section headers having been renamed.

Run from the project root:  python DSH/middleware/patch_raster_revert_edge2.py
"""
import io

CUR = "Middlewares/RASTER/raster2d.cpp"
BAK = "save/26-11-15-09-43/raster2d.cpp.before_fixedpoint"

K_EDGE = "三条边的 x(y)"
K_UV = "UV / 颜色梯度"
K_ROW_BAK = "float fy = (float)y + 0.5f;"
K_ROW_CUR = "int32_t yc = (y << SUBPIXEL_BITS)"
K_ROW_END = "if (xa < bx0) { xa = bx0; }"


def block(text, k_start, k_end, from_index=0):
    i = text.find(k_start, from_index)
    if i < 0:
        raise SystemExit("start key not found: %s" % k_start)
    i = text.rfind("\n", 0, i) + 1

    j = text.find(k_end, i)
    if j < 0:
        raise SystemExit("end key not found: %s" % k_end)
    j = text.rfind("\n", 0, j) + 1

    return i, j


def main():
    cur = io.open(CUR, encoding="utf-8").read()
    bak = io.open(BAK, encoding="utf-8").read()

    if "e_step16" not in cur:
        print("already reverted")
        return

    # --- 边 x(y) ---
    bi0, bi1 = block(bak, K_EDGE, K_UV)
    new_edge = bak[bi0:bi1]

    ci0, ci1 = block(cur, K_EDGE, K_UV)
    cur = cur[:ci0] + new_edge + cur[ci1:]

    # --- 行求交 ---
    bi0, bi1 = block(bak, K_ROW_BAK, K_ROW_END)
    new_row = bak[bi0:bi1]

    ci0, ci1 = block(cur, K_ROW_CUR, K_ROW_END)
    cur = cur[:ci0] + new_row + cur[ci1:]

    # 行内 UV/颜色统一用 fy
    cur = cur.replace("fyf", "fy")

    io.open(CUR, "w", encoding="utf-8", newline="").write(cur)
    print("reverted edge intersection to float")


if __name__ == "__main__":
    main()
