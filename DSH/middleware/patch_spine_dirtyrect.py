#!/usr/bin/env python3
"""Replace the full-screen clear in spine_play with a bbox clear, and add a
clear/draw timing breakdown.

Run from the project root:  python DSH/middleware/patch_spine_dirtyrect.py
"""
import io

PATH = "User/spine_test.cpp"

HELPER = r'''
static void clear_rect(raster_surface_t *s, int x0, int y0, int x1, int y1, uint16_t color)
{
    if (x0 < s->clip_x0) { x0 = s->clip_x0; }
    if (y0 < s->clip_y0) { y0 = s->clip_y0; }
    if (x1 > s->clip_x1) { x1 = s->clip_x1; }
    if (y1 > s->clip_y1) { y1 = s->clip_y1; }
    if ((x0 > x1) || (y0 > y1)) { return; }

    for (int y = y0; y <= y1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        for (int x = x0; x <= x1; x++)
        {
            row[x] = color;
        }
    }
}

'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "clear_rect" in s:
        print("already patched")
        return

    # 1) helper before spine_play
    anchor = 'extern "C" uint8_t spine_play('
    s = s.replace(anchor, HELPER.rstrip() + "\n\n" + anchor, 1)

    # 2) bbox + timers after the fit printf
    fit_anchor = '    printf("[SPN] playback fit: scale=%.3f ox=%.0f oy=%.0f\\r\\n", scale, ox, oy);'
    fit_new = fit_anchor + r'''

    /* 角色在屏幕上的包围盒（用于局部清屏，省掉 70% 的清屏像素） */
    int bx0 = (int)(wminx * scale + ox) - 4;
    int by0 = (int)(wminy * scale + oy) - 4;
    int bx1 = (int)(wmaxx * scale + ox) + 4;
    int by1 = (int)(wmaxy * scale + oy) + 4;

    printf("[SPN] dirty rect: (%d,%d)-(%d,%d) = %d%% of screen\r\n",
           bx0, by0, bx1, by1,
           (int)(100.0f * (float)((bx1 - bx0 + 1) * (by1 - by0 + 1)) / (float)(SCR_W * SCR_H)));

    uint32_t clear_cycles = 0;
    uint32_t draw_cycles = 0;'''
    if fit_anchor not in s:
        raise SystemExit("fit anchor not found")
    s = s.replace(fit_anchor, fit_new, 1)

    # 3) replace the full clear + draw with timed clear_rect + draw
    old = """        raster_clear(&s_surf, 0x0861u);
        draw_commands(renderer.render(skeleton), scale, ox, oy);"""
    new = """        uint32_t tc0 = DWT->CYCCNT;

        clear_rect(&s_surf, bx0, by0, bx1, by1, 0x0861u);

        uint32_t tc1 = DWT->CYCCNT;

        draw_commands(renderer.render(skeleton), scale, ox, oy);

        uint32_t tc2 = DWT->CYCCNT;

        clear_cycles += tc1 - tc0;
        draw_cycles += tc2 - tc1;"""
    if old not in s:
        raise SystemExit("clear anchor not found")
    s = s.replace(old, new, 1)

    # 4) report breakdown once per second
    old_rep = '''            printf("[SPN] t=%.1fs  avg %.2f ms  min %.2f  max %.2f  (%.1f fps)\\r\\n",
                   (float)(f + 1) / (float)fps, avg, min_ms, max_ms, 1000.0f / avg);'''
    new_rep = '''            printf("[SPN] t=%.1fs  avg %.2f ms  min %.2f  max %.2f  (%.1f fps)"
                   "  clear %.2f ms / draw %.2f ms\\r\\n",
                   (float)(f + 1) / (float)fps, avg, min_ms, max_ms, 1000.0f / avg,
                   (float)clear_cycles / 480000.0f / (float)stat_frames,
                   (float)draw_cycles / 480000.0f / (float)stat_frames);

            clear_cycles = 0;
            draw_cycles = 0;'''
    if old_rep not in s:
        raise SystemExit("report anchor not found")
    s = s.replace(old_rep, new_rep, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("dirty-rect clear + timing breakdown installed")


if __name__ == "__main__":
    main()
