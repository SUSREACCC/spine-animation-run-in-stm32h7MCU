#!/usr/bin/env python3
"""Rewrite spine_play() with triple buffering.

With two buffers the sequence was:
    draw into back -> request VBR swap -> immediately draw into the old front
but the old front is still being scanned until the *next* vertical blank, so the
viewer sees the clear rect (a tall dark band) flash over the character.

Triple buffering fixes it: the buffer we draw into is never the one on screen and
never the pending one.

Run from the project root:  python DSH/middleware/patch_spine_triplebuf.py
"""
import io

PATH = "User/spine_test.cpp"

NEW_FUNC = r'''
/*----------------------------------------------------------------- 实时播放（三缓冲） */

#define FB_BUF1 ((uint16_t *)0xC1A00000u)      /* 第二块帧缓冲 */
#define FB_BUF2 ((uint16_t *)0xC1B00000u)      /* 第三块帧缓冲 */

static void ltdc_set_framebuffer(uint16_t *addr)
{
    LTDC_Layer1->CFBAR = (uint32_t)addr;
    LTDC->SRCR = LTDC_SRCR_VBR;                /* 垂直回扫时生效，避免撕裂 */
}

extern "C" uint8_t spine_play(const char *skel_path, const char *atlas_path,
                              const char *anim, int fps, int seconds)
{
    printf("\r\n[SPN] realtime playback: %s @ %d fps for %d s (triple buffered)\r\n", anim, fps, seconds);

    s_arena_used = 0;
    s_verts = (raster_vertex_t *)arena_alloc(sizeof(raster_vertex_t) * SPINE_MAX_VERTS);

    if (s_verts == nullptr)
    {
        return 4;
    }

    RawTextureLoader loader;
    spine::Atlas atlas(atlas_path, &loader);

    if (atlas.getPages().size() == 0)
    {
        printf("[SPN] atlas load FAILED\r\n");
        return 1;
    }

    for (size_t i = 0; i < atlas.getRegions().size(); i++)
    {
        spine::AtlasRegion *r = atlas.getRegions()[i];

        if (r->getPage() != nullptr)
        {
            r->setRendererObject(r->getPage()->texture);
        }
    }

    spine::AtlasAttachmentLoader attachment_loader(atlas);
    spine::SkeletonBinary        binary(attachment_loader, false);
    spine::SkeletonData         *sd = binary.readSkeletonDataFile(skel_path);

    if (sd == nullptr)
    {
        printf("[SPN] skeleton load FAILED\r\n");
        return 2;
    }

    spine::Skeleton           skeleton(*sd);
    spine::AnimationStateData asd(*sd);
    spine::AnimationState     state(asd);
    spine::SkeletonRenderer   renderer;

    skeleton.setupPose();
    skeleton.updateWorldTransform(spine::Physics_Update);

    float wminx = 1e9f, wmaxx = -1e9f, wminy = 1e9f, wmaxy = -1e9f;
    {
        spine::RenderCommand *m = renderer.render(skeleton);

        while (m != nullptr)
        {
            for (int i = 0; i < m->numVertices; i++)
            {
                float x = m->positions[2 * i + 0];
                float y = m->positions[2 * i + 1];

                if (x < wminx) { wminx = x; }
                if (x > wmaxx) { wmaxx = x; }
                if (y < wminy) { wminy = y; }
                if (y > wmaxy) { wmaxy = y; }
            }
            m = m->next;
        }
    }

    if ((wmaxx <= wminx) || (wmaxy <= wminy))
    {
        return 5;
    }

    const float margin_top = 20.0f;
    const float margin_bot = 20.0f;

    float sx = (SCR_W - 80.0f) / (wmaxx - wminx);
    float sy = (SCR_H - margin_top - margin_bot) / (wmaxy - wminy);
    float scale = (sx < sy) ? sx : sy;

    float ox = (SCR_W - (wminx + wmaxx) * scale) * 0.5f;
    float oy = margin_top - wminy * scale;

    printf("[SPN] playback fit: scale=%.3f ox=%.0f oy=%.0f\r\n", scale, ox, oy);

    /* ---- 三块缓冲：画的那块永远既不是正在显示的，也不是待切换的 ---- */
    uint16_t *bufs[3] = { (uint16_t *)FB_ADDR, FB_BUF1, FB_BUF2 };

    s_surf.px = bufs[0];
    s_surf.w = SCR_W;
    s_surf.h = SCR_H;
    s_surf.stride = SCR_W;
    s_surf.clip_x0 = 0;
    s_surf.clip_y0 = 0;
    s_surf.clip_x1 = SCR_W - 1;
    s_surf.clip_y1 = SCR_H - 1;

    for (int i = 0; i < 3; i++)
    {
        raster_clear_init:
        s_surf.px = bufs[i];
        raster_clear(&s_surf, 0x0861u);
        raster_flush(bufs[i], SCR_W * SCR_H * 2);
    }

    s_surf.px = bufs[0];
    ltdc_set_framebuffer(bufs[0]);

    /* 每块缓冲各自的上一帧包围盒（三缓冲 => 3 帧延迟） */
    int pbx[3], pby[3], pbX[3], pbY[3];

    for (int i = 0; i < 3; i++)
    {
        pbx[i] = 0; pby[i] = 0; pbX[i] = -1; pbY[i] = -1;
    }

    state.setAnimation(0, spine::String(anim), true);

    const float dt = 1.0f / (float)fps;
    int total_frames = fps * seconds;
    uint32_t stat_t0 = DWT->CYCCNT;
    int stat_frames = 0;
    float min_ms = 1e9f, max_ms = 0.0f;
    uint32_t clear_cycles = 0;
    uint32_t draw_cycles = 0;

    int draw_idx = 1;

    for (int f = 0; f < total_frames; f++)
    {
        uint32_t f0 = DWT->CYCCNT;

        state.update(dt);
        state.apply(skeleton);
        skeleton.updateWorldTransform(spine::Physics_Update);

        uint16_t *dst = bufs[draw_idx];
        s_surf.px = dst;

        spine::RenderCommand *cmd_list = renderer.render(skeleton);

        uint32_t tc0 = DWT->CYCCNT;

        int cbx0, cby0, cbx1, cby1;
        commands_bbox(cmd_list, scale, ox, oy, &cbx0, &cby0, &cbx1, &cby1);

        int dbx0 = (pbX[draw_idx] < 0) ? cbx0 : ((cbx0 < pbx[draw_idx]) ? cbx0 : pbx[draw_idx]);
        int dby0 = (pbX[draw_idx] < 0) ? cby0 : ((cby0 < pby[draw_idx]) ? cby0 : pby[draw_idx]);
        int dbx1 = (pbX[draw_idx] < 0) ? cbx1 : ((cbx1 > pbX[draw_idx]) ? cbx1 : pbX[draw_idx]);
        int dby1 = (pbX[draw_idx] < 0) ? cby1 : ((cby1 > pbY[draw_idx]) ? cby1 : pbY[draw_idx]);

        clear_rect(&s_surf, dbx0, dby0, dbx1, dby1, 0x0861u);

        uint32_t tc1 = DWT->CYCCNT;

        draw_commands(cmd_list, scale, ox, oy);

        uint32_t tc2 = DWT->CYCCNT;

        clear_cycles += tc1 - tc0;
        draw_cycles += tc2 - tc1;

        pbx[draw_idx] = cbx0;
        pby[draw_idx] = cby0;
        pbX[draw_idx] = cbx1;
        pbY[draw_idx] = cby1;

        raster_flush(dst, SCR_W * SCR_H * 2);

        /* 上一次的 VBR 完成后再请求下一次，保证切换序列不重叠 */
        while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
        {
        }

        ltdc_set_framebuffer(dst);

        /* 三缓冲：轮到下一块，它既不显示、也不在待切换状态 */
        draw_idx = (draw_idx + 1) % 3;

        float ms = (float)(DWT->CYCCNT - f0) / 480000.0f;

        if (ms < min_ms) { min_ms = ms; }
        if (ms > max_ms) { max_ms = ms; }

        stat_frames++;

        if (ms < (float)(1000 / fps))
        {
            delay_ms((uint16_t)((float)(1000 / fps) - ms));
        }

        if (stat_frames >= fps)
        {
            float avg = (float)(DWT->CYCCNT - stat_t0) / 480000.0f / (float)stat_frames;

            printf("[SPN] t=%.1fs  avg %.2f ms  min %.2f  max %.2f  (%.1f fps)"
                   "  clear %.2f ms / draw %.2f ms\r\n",
                   (float)(f + 1) / (float)fps, avg, min_ms, max_ms, 1000.0f / avg,
                   (float)clear_cycles / 480000.0f / (float)stat_frames,
                   (float)draw_cycles / 480000.0f / (float)stat_frames);

            stat_t0 = DWT->CYCCNT;
            stat_frames = 0;
            min_ms = 1e9f;
            max_ms = 0.0f;
            clear_cycles = 0;
            draw_cycles = 0;
        }
    }

    ltdc_set_framebuffer(bufs[0]);

    printf("[SPN] playback done (%d frames)\r\n", total_frames);
    printf("[SPN] RESULT PASS\r\n");
    return 0;
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "三缓冲" in s:
        print("triple buffering already present")
        return

    marker = 'extern "C" uint8_t spine_play('
    i = s.find(marker)

    if i < 0:
        raise SystemExit("spine_play not found")

    # 也删掉旧的 FB_BACK / ltdc_set_framebuffer 定义（在新函数里重新定义）
    head = s[:i]
    old_start = head.rfind('/*----------------------------------------------------------------- 实时播放 */')
    if old_start > 0:
        head = head[:old_start]

    s = head.rstrip() + "\n\n" + NEW_FUNC.lstrip()
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("spine_play replaced with triple-buffered version")


if __name__ == "__main__":
    main()
