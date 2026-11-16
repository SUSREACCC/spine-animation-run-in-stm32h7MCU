#!/usr/bin/env python3
"""Give each of the three framebuffers its OWN low-res render buffer.

Root cause of the remaining trails / flicker / "layers missing":

    framebuffer X is written every 3 frames, so it holds frame N-3,
    but the single shared low-res buffer always holds frame N.
    Upscaling the dirty rect into X therefore read pixels that belong to
    OTHER frames, mixing frame N-3, N-1 and N content on screen.

With one low-res buffer per framebuffer, the (current bbox + this buffer's
previous bbox) clear/upscale rule becomes correct again, exactly as it was for
the full-resolution path.

Run from the project root:  python DSH/middleware/patch_spine_lowbufs.py
"""
import io

PATH = "User/spine_test.cpp"

OLD_ALLOC = r'''    uint16_t *low = (uint16_t *)arena_alloc((uint32_t)RW * RH * 2u);
    uint16_t *bufs[3] = { (uint16_t *)FB_ADDR, FB_BUF1, FB_BUF2 };

    if (low == nullptr)
    {
        printf("[SPN] low-res buffer alloc failed\r\n");
        return 6;
    }'''

NEW_ALLOC = r'''    /* 三块低分辨率缓冲：与三块前台缓冲一一对应。
     * 共用一块会让"第 N 帧的内容"混进"第 N-3 帧的缓冲"，产生叠影/闪烁。 */
    uint16_t *lows[3];
    uint16_t *bufs[3] = { (uint16_t *)FB_ADDR, FB_BUF1, FB_BUF2 };

    for (int i = 0; i < 3; i++)
    {
        lows[i] = (uint16_t *)arena_alloc((uint32_t)RW * RH * 2u);

        if (lows[i] == nullptr)
        {
            printf("[SPN] low-res buffer alloc failed\r\n");
            return 6;
        }
    }'''

OLD_CLEAR = r'''    rs.px = low;
    raster_clear(&rs, 0x0861u);
    raster_flush(low, RW * RH * 2);'''

NEW_CLEAR = r'''    for (int i = 0; i < 3; i++)
    {
        rs.px = lows[i];
        raster_clear(&rs, 0x0861u);
        raster_flush(lows[i], RW * RH * 2);
    }'''

OLD_SEL1 = "    rs.px = (divisor == 1) ? bufs[0] : low;"
NEW_SEL1 = "    rs.px = (divisor == 1) ? bufs[0] : lows[0];"

OLD_SEL2 = "        rs.px = (divisor == 1) ? dst : low;"
NEW_SEL2 = "        rs.px = (divisor == 1) ? dst : lows[draw_idx];"

OLD_FLUSH = """            raster_flush(low, RW * RH * 2);

            /* 只放大脏矩形 */
            raster_upscale2x(low, RW, dst, SCR_W, dbx0, dby0, dbx1, dby1);"""
NEW_FLUSH = """            raster_flush(lows[draw_idx], RW * RH * 2);

            /* 只放大脏矩形（从"本缓冲专属"的低分辨率缓冲读） */
            raster_upscale2x(lows[draw_idx], RW, dst, SCR_W, dbx0, dby0, dbx1, dby1);"""


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "lows[3]" in s:
        print("already patched")
        return

    for old, new in ((OLD_ALLOC, NEW_ALLOC), (OLD_CLEAR, NEW_CLEAR),
                     (OLD_SEL1, NEW_SEL1), (OLD_SEL2, NEW_SEL2),
                     (OLD_FLUSH, NEW_FLUSH)):
        if old not in s:
            raise SystemExit("block not found: %r" % old[:60])
        s = s.replace(old, new, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("per-framebuffer low-res buffers installed")


if __name__ == "__main__":
    main()
