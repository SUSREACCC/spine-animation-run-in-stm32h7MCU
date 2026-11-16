#!/usr/bin/env python3
"""Fix the world->screen mapping in User/spine_test.cpp.

The spineboy-pro rig has its world Y increasing downward (bounds -678..8 with
the head near 0), so flipping Y made the character render upside down.  Map
straight through instead and derive the offsets from the measured bounds.

Run from the project root:  python DSH/middleware/patch_spine_orient.py
"""
import io

PATH = "User/spine_test.cpp"

OLD_Y = "                verts[i].y = (float)SCR_H - (y * scale + oy);"
NEW_Y = "                verts[i].y = y * scale + oy;"

OLD_OX = "    float ox = (SCR_W - (wminx + wmaxx) * scale) * 0.5f;"
NEW_OX = ("    float ox = margin_x + (SCR_W - 2 * margin_x - (wmaxx - wminx) * scale) * 0.5f\n"
          "               - wminx * scale;")

OLD_OY = "    float oy = SCR_H - margin_top - wmaxy * scale;"
NEW_OY = "    float oy = margin_top - wminy * scale;"


def main():
    s = io.open(PATH, encoding="utf-8").read()
    n = 0

    for old, new in ((OLD_Y, NEW_Y), (OLD_OX, NEW_OX), (OLD_OY, NEW_OY)):
        if old in s:
            s = s.replace(old, new, 1)
            n += 1

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("replaced %d/3 anchors" % n)


if __name__ == "__main__":
    main()
