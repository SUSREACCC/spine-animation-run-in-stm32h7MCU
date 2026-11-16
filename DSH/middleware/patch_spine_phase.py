#!/usr/bin/env python3
"""Replace the coarse clear/raster/present timing in spine_play_duo with five
phase timers: anim, build (renderer.render + bbox), clear, draw, present.

The old numbers were self-contradictory (raster 3.17 ms inside a 47 ms frame),
so a phase-level breakdown is needed before drawing conclusions.

Run from the project root:  python DSH/middleware/patch_spine_phase.py
"""
import io

PATH = "User/spine_test.cpp"

OLD_LOOP_START = """            uint32_t fr0 = DWT->CYCCNT;

            stA->update(dt);"""

NEW_LOOP_START = """            uint32_t fr0 = DWT->CYCCNT;

            uint32_t p0 = fr0;

            stA->update(dt);"""

OLD_AFTER_WORLD = """            uint16_t *dst = bufs[draw_idx];
            rs.px = (divisor == 1) ? dst : lows[draw_idx];"""

NEW_AFTER_WORLD = """            uint32_t p1 = DWT->CYCCNT;      /* 动画结束 */

            uint16_t *dst = bufs[draw_idx];
            rs.px = (divisor == 1) ? dst : lows[draw_idx];"""

OLD_CLEAR = """            uint32_t c0 = DWT->CYCCNT;
            clear_rect(&rs, dbx0, dby0, dbx1, dby1, 0x0861u);
            uint32_t c1 = DWT->CYCCNT;"""

NEW_CLEAR = """            uint32_t p2 = DWT->CYCCNT;      /* 构建命令 + 包围盒结束 */

            uint32_t c0 = DWT->CYCCNT;
            clear_rect(&rs, dbx0, dby0, dbx1, dby1, 0x0861u);
            uint32_t c1 = DWT->CYCCNT;"""

OLD_ACC = """            clr_cyc += c1 - c0;
            ras_cyc += c2 - c1;"""

NEW_ACC = """            clr_cyc += c1 - c0;
            ras_cyc += c2 - c1;

            anim_cyc += p1 - p0;
            build_cyc += p2 - p1;"""

OLD_DECL = """        uint32_t clr_cyc = 0, ras_cyc = 0, pre_cyc = 0;"""

NEW_DECL = """        uint32_t clr_cyc = 0, ras_cyc = 0, pre_cyc = 0;
        uint32_t anim_cyc = 0, build_cyc = 0;"""

OLD_PRE = """            pre_cyc += DWT->CYCCNT - c2;"""

NEW_PRE = """            pre_cyc += DWT->CYCCNT - c2;"""

OLD_PRINT = '''        printf("[DUO] it%d load %.1f ms (tex %.1f + read %.1f + parse %.1f, blocks %lu) | %.2f ms/frame (%.1f fps) | clear %.2f raster %.2f present %.2f | heap %lu->%lu peak %lu fails %lu\\r\\n",'''
NEW_PRINT = '''        printf("[DUO] it%d load %.1f ms | %.2f ms/frame (%.1f fps) | anim %.2f build %.2f clear %.2f draw %.2f present %.2f | heap %lu fails %lu\\r\\n",'''

OLD_ARGS = """               it + 1, load_ms,
               (float)(t_tex1 - t_tex0) / 480000.0f,
               (float)(t_r1 - t_r0) / 480000.0f,
               (float)(t_r2 - t_r1) / 480000.0f,
               (unsigned long)spine_heap_block_count(),
               frame_ms, 1000.0f / frame_ms,
               (float)clr_cyc / 480000.0f / (float)total_frames,
               (float)ras_cyc / 480000.0f / (float)total_frames,
               (float)pre_cyc / 480000.0f / (float)total_frames,
               (unsigned long)hs0.used_bytes, (unsigned long)hs1.used_bytes,
               (unsigned long)hs1.peak_bytes, (unsigned long)hs1.fail_count);"""

NEW_ARGS = """               it + 1, load_ms,
               frame_ms, 1000.0f / frame_ms,
               (float)anim_cyc / 480000.0f / (float)total_frames,
               (float)build_cyc / 480000.0f / (float)total_frames,
               (float)clr_cyc / 480000.0f / (float)total_frames,
               (float)ras_cyc / 480000.0f / (float)total_frames,
               (float)pre_cyc / 480000.0f / (float)total_frames,
               (unsigned long)hs1.used_bytes, (unsigned long)hs1.fail_count);"""


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "anim_cyc" in s:
        print("already patched")
        return

    for old, new in ((OLD_DECL, NEW_DECL), (OLD_LOOP_START, NEW_LOOP_START),
                     (OLD_AFTER_WORLD, NEW_AFTER_WORLD), (OLD_CLEAR, NEW_CLEAR),
                     (OLD_ACC, NEW_ACC), (OLD_PRINT, NEW_PRINT), (OLD_ARGS, NEW_ARGS)):
        if old not in s:
            raise SystemExit("block not found: %r" % old[:60])
        s = s.replace(old, new, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("five-phase timing installed")


if __name__ == "__main__":
    main()
