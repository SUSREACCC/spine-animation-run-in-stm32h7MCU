#!/usr/bin/env python3
"""Overlay API v2: draw the overlay at FULL resolution, every frame.

Why v1 was wrong
----------------
v1 flushed the overlay into the *render* surface, so at divisor=2 the 16 px font
was rendered into a 400x240 buffer and then upscaled 2x -> blurry.  On top of
that, a per-buffer "generation" scheme made the three framebuffers show
different overlay content for a couple of frames -> visible flicker.

v2
--
* Overlay ops are drawn into the full-resolution target (dst) AFTER the
  half-res upscale (or after the instances when divisor == 1).
  => text is always crisp, independent of the spine resolution.
* Drawn every frame, so all three buffers always agree => no flicker.
* The HUD bands are opaque fills queued before the text, so old glyphs are
  erased naturally.
* No dirty-rect participation: unchanged spine frames stay on the fast path.
* Cache: the overlay bbox rows are cleaned explicitly when needed.

Run from the project root:  python DSH/middleware/patch_overlay_v2.py
"""
import io

CPP = "User/spine_api.cpp"


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "ov_draw_fullres" in s:
        print("already v2")
        return

    # ---------------------------------------------------------------- 1. 去掉代次机制
    old_gen = """    int idx = g_d.draw_idx;
    int ov_redraw = 0;

    /* ---- 覆盖层：内容变了才重画，并且每个缓冲只吸收一次 ---- */
    if (g_ov_count > 0)
    {
        int changed = (g_ov_count != g_ov_prev_count) ||
                      (memcmp(g_ov, g_ov_prev,
                              sizeof(spine_ov_op_t) * (size_t)g_ov_count) != 0);

        if (changed)
        {
            memcpy(g_ov_prev, g_ov, sizeof(spine_ov_op_t) * (size_t)g_ov_count);
            g_ov_prev_count = g_ov_count;
            g_ov_gen++;
        }

        if (g_d.buf_ov_gen[idx] != g_ov_gen)
        {
            ov_redraw = 1;
            g_d.buf_ov_gen[idx] = g_ov_gen;

            if (g_ov_have_bbox)
            {
                if (!g_d.have_bbox)
                {
                    g_d.fbx0 = g_ov_bx0;
                    g_d.fby0 = g_ov_by0;
                    g_d.fbx1 = g_ov_bx1;
                    g_d.fby1 = g_ov_by1;
                    g_d.have_bbox = 1;
                }
                else
                {
                    if (g_ov_bx0 < g_d.fbx0) { g_d.fbx0 = g_ov_bx0; }
                    if (g_ov_by0 < g_d.fby0) { g_d.fby0 = g_ov_by0; }
                    if (g_ov_bx1 > g_d.fbx1) { g_d.fbx1 = g_ov_bx1; }
                    if (g_ov_by1 > g_d.fby1) { g_d.fby1 = g_ov_by1; }
                }
            }
        }
    }
"""
    assert old_gen in s, "generation block not found"
    s = s.replace(old_gen, "    int idx = g_d.draw_idx;\n", 1)

    # 不再在低分辨率表面上画覆盖层
    old_flush = """    /* 覆盖层画在实例之上（内容变了才重画） */
    if (ov_redraw)
    {
        spine_overlay_flush(&g_d.surf, (g_d.divisor == 1) ? 1.0f : 0.5f);
    }
"""
    assert old_flush in s, "low-res flush not found"
    s = s.replace(old_flush, "", 1)

    # ---------------------------------------------------------------- 2. 全分辨率绘制
    old_tail = """    /* 记录本帧包围盒，供该缓冲三帧后再用 */"""
    new_tail = """    /* ---- 覆盖层：直接画到全分辨率目标（放大之后），文字清晰且每帧一致 ---- */
    if (g_ov_count > 0)
    {
        raster_surface_t full;

        full.px = dst;
        full.w = SPINE_SCR_W;
        full.h = SPINE_SCR_H;
        full.stride = SPINE_SCR_W;
        full.clip_x0 = 0;
        full.clip_y0 = 0;
        full.clip_x1 = SPINE_SCR_W - 1;
        full.clip_y1 = SPINE_SCR_H - 1;

        spine_overlay_flush(&full, 1.0f);

        if (plat_fb_need_cache_clean() && g_ov_have_bbox)
        {
            int oy;

            for (oy = g_ov_by0; oy <= g_ov_by1; oy++)
            {
                int x0 = (g_ov_bx0 < 0) ? 0 : g_ov_bx0;
                int x1 = (g_ov_bx1 > SPINE_SCR_W - 1) ? (SPINE_SCR_W - 1) : g_ov_bx1;

                if ((oy < 0) || (oy > SPINE_SCR_H - 1) || (x1 < x0))
                {
                    continue;
                }

                plat_cache_clean(dst + (size_t)oy * SPINE_SCR_W + x0,
                                 (size_t)(x1 - x0 + 1) * 2u);
            }
        }
    }

    /* 记录本帧包围盒，供该缓冲三帧后再用 */"""
    assert old_tail in s
    s = s.replace(old_tail, new_tail, 1)

    # ---------------------------------------------------------------- 3. 清理不再使用的静态量
    s = s.replace("""static spine_ov_op_t g_ov_prev[SPINE_OV_MAX];
static int           g_ov_count = 0;
static int           g_ov_prev_count = 0;
static uint32_t      g_ov_gen = 1;             /* 覆盖层内容代次 */
""", """static int           g_ov_count = 0;
""")

    s = s.replace("        g_d.buf_ov_gen[i] = 0;         /* 缓冲被清空：覆盖层需要重画 */\n", "")

    s = s.replace("""    uint16_t *bufs[3];
    uint32_t         buf_ov_gen[3];              /* 每个缓冲已吸收的覆盖层代次 */""",
                  """    uint16_t *bufs[3];""")

    # g_ov_have_bbox 仍然需要（给缓存清理用），保留声明
    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("overlay v2: full-resolution, every frame")


if __name__ == "__main__":
    main()
