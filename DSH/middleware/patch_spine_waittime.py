#!/usr/bin/env python3
"""Instrument the vsync wait in spine_play_duo so the per-frame accounting closes.

Current state: half-res phases sum exactly to the frame time, but full-res leaves
~74 ms unaccounted.  The only unmeasured block is the
`while (LTDC->SRCR & LTDC_SRCR_VBR)` wait, so time it explicitly.

Run from the project root:  python DSH/middleware/patch_spine_waittime.py
"""
import io

PATH = "User/spine_test.cpp"


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "wait_cyc" in s:
        print("already patched")
        return

    old_decl = """        uint32_t anim_cyc = 0, build_cyc = 0;"""
    new_decl = """        uint32_t anim_cyc = 0, build_cyc = 0;
        uint32_t wait_cyc = 0;"""
    if old_decl not in s:
        raise SystemExit("decl not found")
    s = s.replace(old_decl, new_decl, 1)

    old_wait = """            while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
            {
            }

            ltdc_set_framebuffer(dst);
            draw_idx = (draw_idx + 1) % 3;"""
    new_wait = """            uint32_t w0 = DWT->CYCCNT;

            while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
            {
            }

            wait_cyc += DWT->CYCCNT - w0;

            ltdc_set_framebuffer(dst);
            draw_idx = (draw_idx + 1) % 3;"""
    if old_wait not in s:
        raise SystemExit("wait block not found")
    s = s.replace(old_wait, new_wait, 1)

    old_print = 'clear %.2f draw %.2f present %.2f | heap %lu fails %lu\\r\\n",'
    new_print = 'clear %.2f draw %.2f present %.2f wait %.2f | heap %lu fails %lu\\r\\n",'
    if old_print not in s:
        raise SystemExit("print fmt not found")
    s = s.replace(old_print, new_print, 1)

    old_args = """               (float)pre_cyc / 480000.0f / (float)total_frames,
               (unsigned long)hs1.used_bytes, (unsigned long)hs1.fail_count);"""
    new_args = """               (float)pre_cyc / 480000.0f / (float)total_frames,
               (float)wait_cyc / 480000.0f / (float)total_frames,
               (unsigned long)hs1.used_bytes, (unsigned long)hs1.fail_count);"""
    if old_args not in s:
        raise SystemExit("print args not found")
    s = s.replace(old_args, new_args, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("vsync wait timer installed")


if __name__ == "__main__":
    main()
