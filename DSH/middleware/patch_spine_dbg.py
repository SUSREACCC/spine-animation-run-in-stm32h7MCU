#!/usr/bin/env python3
"""Insert a 3-frame debug print into spine_play to capture:
   frame index, draw_idx, target pointer, dirty rect, and the pixel value that
   actually landed in the target buffer after the upscale.

Run from the project root:  python DSH/middleware/patch_spine_dbg.py
"""
import io

PATH = "User/spine_test.cpp"

BEFORE = r'''        uint16_t *dst = bufs[draw_idx];
'''

BEFORE_NEW = r'''        uint16_t *dst = bufs[draw_idx];

        bool dbg_this = (f < 3);
'''

AFTER = r'''        present_cycles += DWT->CYCCNT - tc2;
'''

AFTER_NEW = r'''        present_cycles += DWT->CYCCNT - tc2;

        if (dbg_this)
        {
            int sx = (2 * dbx0 + 2 * dbx1) / 2;
            int sy = (2 * dby0 + 2 * dby1) / 2;

            if (sx > SCR_W - 1) { sx = SCR_W - 1; }
            if (sy > SCR_H - 1) { sy = SCR_H - 1; }

            printf("[DBG] f=%d idx=%d dst=%p rect=(%d,%d)-(%d,%d) px@(%d,%d)=%04X\r\n",
                   f, draw_idx, (void *)dst, dbx0, dby0, dbx1, dby1, sx, sy,
                   (unsigned)dst[(size_t)sy * SCR_W + sx]);
        }
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "[DBG] f=" in s:
        print("already patched")
        return

    if BEFORE not in s or AFTER not in s:
        raise SystemExit("anchors not found")

    s = s.replace(BEFORE, BEFORE_NEW, 1)
    s = s.replace(AFTER, AFTER_NEW, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("debug prints inserted")


if __name__ == "__main__":
    main()
