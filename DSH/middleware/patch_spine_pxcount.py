#!/usr/bin/env python3
"""Use the rasterizer pixel counter in spine_play_duo: report how many pixels per
frame actually reach the rasterizer.

Run from the project root:  python DSH/middleware/patch_spine_pxcount.py
"""
import io

PATH = "User/spine_test.cpp"

DECL = """extern "C" void raster_pixel_reset(void);
extern "C" uint32_t raster_pixel_count(void);

"""


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "raster_pixel_count" in s:
        print("already patched")
        return

    # extern 声明放在 raster_upscale2x 使用处之前
    anchor = "/*----------------------------------------------------------------- 双角色 + 反复重载 */"
    if anchor not in s:
        raise SystemExit("duo anchor not found")
    s = s.replace(anchor, DECL + anchor, 1)

    # 循环里累加像素数
    old = """        uint32_t anim_cyc = 0, build_cyc = 0;"""
    new = """        uint32_t anim_cyc = 0, build_cyc = 0;
        uint64_t px_sum = 0;"""
    if old not in s:
        raise SystemExit("decl not found")
    s = s.replace(old, new, 1)

    old_draw = """            uint32_t c1 = DWT->CYCCNT;

            draw_commands(cA, A.scale, A.ox, A.oy, &rs);
            draw_commands(cB, B.scale, B.ox, B.oy, &rs);
            uint32_t c2 = DWT->CYCCNT;"""
    new_draw = """            uint32_t c1 = DWT->CYCCNT;

            raster_pixel_reset();
            draw_commands(cA, A.scale, A.ox, A.oy, &rs);
            draw_commands(cB, B.scale, B.ox, B.oy, &rs);
            px_sum += raster_pixel_count();
            uint32_t c2 = DWT->CYCCNT;"""
    if old_draw not in s:
        raise SystemExit("draw block not found")
    s = s.replace(old_draw, new_draw, 1)

    old_print = 'clear %.2f draw %.2f present %.2f | heap %lu fails %lu\\r\\n",'
    new_print = 'clear %.2f draw %.2f present %.2f | %.1f kpx/frame | heap %lu fails %lu\\r\\n",'
    if old_print not in s:
        raise SystemExit("print fmt not found")
    s = s.replace(old_print, new_print, 1)

    old_args = """               (float)pre_cyc / 480000.0f / (float)total_frames,
               (unsigned long)hs1.used_bytes, (unsigned long)hs1.fail_count);"""
    new_args = """               (float)pre_cyc / 480000.0f / (float)total_frames,
               (double)px_sum / 1000.0 / (double)total_frames,
               (unsigned long)hs1.used_bytes, (unsigned long)hs1.fail_count);"""
    if old_args not in s:
        raise SystemExit("print args not found")
    s = s.replace(old_args, new_args, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("pixel count wired into duo")


if __name__ == "__main__":
    main()
