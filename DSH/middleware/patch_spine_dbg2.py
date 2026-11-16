#!/usr/bin/env python3
"""Replace the single-point debug sample in spine_play with a checksum over the
whole upscaled rectangle (line based, avoids backslash escaping issues).

Run from the project root:  python DSH/middleware/patch_spine_dbg2.py
"""
import io

PATH = "User/spine_test.cpp"

NEW = [
    "            uint32_t rect_sum = 0;",
    "",
    "            for (int yy = 2 * dby0; yy <= 2 * dby1; yy += 7)",
    "            {",
    "                const uint16_t *rr = dst + (size_t)yy * SCR_W;",
    "",
    "                for (int xx = 2 * dbx0; xx <= 2 * dbx1; xx += 5)",
    "                {",
    "                    rect_sum = rect_sum * 31u + rr[xx];",
    "                }",
    "            }",
    "",
    '            printf("[DBG] f=%d idx=%d dst=%p rect=(%d,%d)-(%d,%d) sum=%08lX corner=%04X\\r\\n",',
    "                   f, draw_idx, (void *)dst, dbx0, dby0, dbx1, dby1,",
    "                   (unsigned long)rect_sum, (unsigned)dst[(size_t)(2 * dby0) * SCR_W + 2 * dbx0]);",
]


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")

    start = None
    for i, ln in enumerate(lines):
        if "int sx = (2 * dbx0" in ln:
            start = i
            break

    if start is None:
        print("anchor not found (already patched?)")
        return

    # 块从 `if (dbg_this)` 之后开始，到 printf 语句结束（3 行）
    # 找到该块的结束：包含 "dst[(size_t)sy * SCR_W + sx]);" 的行
    end = None
    for j in range(start, min(start + 20, len(lines))):
        if "sy * SCR_W + sx]);" in lines[j]:
            end = j
            break

    if end is None:
        print("end not found")
        return

    lines[start:end + 1] = NEW
    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(lines))
    print("debug block replaced (lines %d..%d)" % (start + 1, end + 1))


if __name__ == "__main__":
    main()
