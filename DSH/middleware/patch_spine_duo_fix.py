#!/usr/bin/env python3
"""Fix three issues found by the duo experiment:

1. SkeletonData was never deleted -> ~350 KB leaked per iteration.
2. Frame time was measured with a single 32-bit DWT delta over the whole loop,
   which wraps every 8.9 s at 480 MHz -> nonsense fps.  Accumulate per frame.
3. Split the load time into texture vs skeleton so the SD read cost is visible.

Run from the project root:  python DSH/middleware/patch_spine_duo_fix.py
"""
import io

PATH = "User/spine_test.cpp"


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "g_duo_fixed" in s:
        print("already patched")
        return

    # --- 1/3: 拆开加载计时 ---
    old_load = """        uint32_t load_cycles = DWT->CYCCNT - t_load0;
        float    load_ms = (float)load_cycles / 480000.0f;"""
    new_load = """        uint32_t load_cycles = DWT->CYCCNT - t_load0;
        float    load_ms = (float)load_cycles / 480000.0f;"""
    # (时间点已经在 atlas 之后统计不了，改成在下方分别打印)

    # 在 atlas 构造前后加计时
    old_atlas = """        RawTextureLoader loader;
        spine::Atlas atlas(atlas_path, &loader);"""
    new_atlas = """        uint32_t t_tex0 = DWT->CYCCNT;

        RawTextureLoader loader;
        spine::Atlas atlas(atlas_path, &loader);

        uint32_t t_tex1 = DWT->CYCCNT;"""
    if old_atlas not in s:
        raise SystemExit("atlas block not found")
    s = s.replace(old_atlas, new_atlas, 1)

    # --- 2: 每帧累加，避免 DWT 32 位回绕 ---
    old_fr = """        uint32_t fr0 = DWT->CYCCNT;
        uint32_t clr_cyc = 0, ras_cyc = 0, pre_cyc = 0;"""
    new_fr = """        uint32_t clr_cyc = 0, ras_cyc = 0, pre_cyc = 0;
        uint64_t frame_cyc_sum = 0;"""
    if old_fr not in s:
        raise SystemExit("frame timer block not found")
    s = s.replace(old_fr, new_fr, 1)

    old_loop_head = """        for (int f = 0; f < total_frames; f++)
        {
            stA->update(dt);"""
    new_loop_head = """        for (int f = 0; f < total_frames; f++)
        {
            uint32_t fr0 = DWT->CYCCNT;

            stA->update(dt);"""
    if old_loop_head not in s:
        raise SystemExit("loop head not found")
    s = s.replace(old_loop_head, new_loop_head, 1)

    old_swap = """            ltdc_set_framebuffer(dst);
            draw_idx = (draw_idx + 1) % 3;
        }

        float frame_ms = (float)(DWT->CYCCNT - fr0) / 480000.0f / (float)total_frames;"""
    new_swap = """            ltdc_set_framebuffer(dst);
            draw_idx = (draw_idx + 1) % 3;

            frame_cyc_sum += (uint32_t)(DWT->CYCCNT - fr0);
        }

        float frame_ms = (float)frame_cyc_sum / 480000.0f / (float)total_frames;"""
    if old_swap not in s:
        raise SystemExit("swap block not found")
    s = s.replace(old_swap, new_swap, 1)

    # --- 3: 打印纹理/骨骼分别耗时 + 删除 SkeletonData ---
    old_print = '''        printf("[DUO] it%d load %.1f ms | %.2f ms/frame (%.1f fps) | clear %.2f raster %.2f present %.2f | heap %lu->%lu peak %lu fails %lu\\r\\n",'''
    new_print = '''        printf("[DUO] it%d load %.1f ms (tex %.1f + skel %.1f) | %.2f ms/frame (%.1f fps) | clear %.2f raster %.2f present %.2f | heap %lu->%lu peak %lu fails %lu\\r\\n",'''
    if old_print not in s:
        raise SystemExit("print block not found")
    s = s.replace(old_print, new_print, 1)

    old_args = '''               it + 1, load_ms, frame_ms, 1000.0f / frame_ms,'''
    new_args = '''               it + 1, load_ms,
               (float)(t_tex1 - t_tex0) / 480000.0f,
               load_ms - (float)(t_tex1 - t_tex0) / 480000.0f,
               frame_ms, 1000.0f / frame_ms,'''
    if old_args not in s:
        raise SystemExit("print args not found")
    s = s.replace(old_args, new_args, 1)

    old_del = """        delete stA;
        delete stB;
        delete skA;
        delete skB;"""
    new_del = """        delete stA;
        delete stB;
        delete skA;
        delete skB;
        delete sd;              /* 之前漏了：SkeletonData 每轮约 350 KB */"""
    if old_del not in s:
        raise SystemExit("delete block not found")
    s = s.replace(old_del, new_del, 1)

    s = s.replace("extern \"C\" uint8_t spine_play_duo(", "static const int g_duo_fixed = 1;\n\nextern \"C\" uint8_t spine_play_duo(", 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("duo fixes applied (leak, DWT wrap, load breakdown)")


if __name__ == "__main__":
    main()
