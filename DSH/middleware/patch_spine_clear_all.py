#!/usr/bin/env python3
"""Clear all three full-size buffers (and the low-res buffer) before playback.

Previously, when running a half-res session after a full-res one, the full-size
buffers still held the previous session's frames.  Since only the dirty rect is
upscaled, the rest of the screen kept showing those stale full-res frames -
"layers that should not be visible" plus heavy flicker.

Run from the project root:  python DSH/middleware/patch_spine_clear_all.py
"""
import io

PATH = "User/spine_test.cpp"

OLD = r'''    for (int i = 0; i < 3; i++)
    {
        rs.px = (divisor == 1) ? bufs[i] : low;
        raster_clear(&rs, 0x0861u);

        if (divisor == 1)
        {
            raster_flush(bufs[i], SCR_W * SCR_H * 2);
        }
    }

    if (divisor > 1)
    {
        raster_flush(low, RW * RH * 2);
    }'''

NEW = r'''    /* 三块全尺寸缓冲全部清干净：半分辨率时只放大脏矩形，
     * 若这里留了上一轮的旧画面，屏幕上就会"看到不该看到的图层"。 */
    for (int i = 0; i < 3; i++)
    {
        raster_surface_t fs;

        fs.px = bufs[i];
        fs.w = SCR_W;
        fs.h = SCR_H;
        fs.stride = SCR_W;
        fs.clip_x0 = 0;
        fs.clip_y0 = 0;
        fs.clip_x1 = SCR_W - 1;
        fs.clip_y1 = SCR_H - 1;

        raster_clear(&fs, 0x0861u);
        raster_flush(bufs[i], SCR_W * SCR_H * 2);
    }

    rs.px = low;
    raster_clear(&rs, 0x0861u);
    raster_flush(low, RW * RH * 2);'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "上一轮的旧画面" in s:
        print("already patched")
        return

    if OLD not in s:
        raise SystemExit("init clear block not found")

    s = s.replace(OLD, NEW, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("full clear of all buffers installed")


if __name__ == "__main__":
    main()
