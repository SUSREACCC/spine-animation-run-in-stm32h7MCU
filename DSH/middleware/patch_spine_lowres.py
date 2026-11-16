#!/usr/bin/env python3
"""Rewrite spine_play() with a `divisor` parameter (1 = full res, 2 = half res).

Half resolution renders the scene into a 400x240 buffer (1/4 of the pixels) and
then upscales ONLY the dirty rectangle 2x into the triple-buffered full-size
frame - upscaling the whole screen would eat most of the saving.

Run from the project root:  python DSH/middleware/patch_spine_lowres.py
"""
import io

PATH = "User/spine_test.cpp"
HEADER = "User/spine_test.h"
SELFTEST = "User/selftest.c"

FUNC = r'''
/*----------------------------------------------------------------- 实时播放（三缓冲 + 可选半分辨率） */

#define FB_BUF1 ((uint16_t *)0xC1A00000u)
#define FB_BUF2 ((uint16_t *)0xC1B00000u)

static void ltdc_set_framebuffer(uint16_t *addr)
{
    LTDC_Layer1->CFBAR = (uint32_t)addr;
    LTDC->SRCR = LTDC_SRCR_VBR;
}

extern "C" uint8_t spine_play(const char *skel_path, const char *atlas_path,
                              const char *anim, int fps, int seconds, int divisor)
{
    if (divisor < 1)
    {
        divisor = 1;
    }

    const int RW = SCR_W / divisor;
    const int RH = SCR_H / divisor;

    printf("\r\n[SPN] playback: %s @ %d fps for %d s | render %dx%d (1/%d pixels)\r\n",
           anim, fps, seconds, RW, RH, divisor * divisor);

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

    /* 适配到渲染分辨率 */
    const float margin_top = 20.0f / (float)divisor;
    const float margin_bot = margin_top;

    float sx = ((float)RW - 80.0f / (float)divisor) / (wmaxx - wminx);
    float sy = ((float)RH - margin_top - margin_bot) / (wmaxy - wminy);
    float scale = (sx < sy) ? sx : sy;

    float ox = ((float)RW - (wminx + wmaxx) * scale) * 0.5f;
    float oy = margin_top - wminy * scale;

    printf("[SPN] fit: scale=%.3f ox=%.0f oy=%.0f (render space)\r\n", scale, ox, oy);

    /* ---- 渲染目标 ---- */
    uint16_t *low = (uint16_t *)arena_alloc((uint32_t)RW * RH * 2u);
    uint16_t *bufs[3] = { (uint16_t *)FB_ADDR, FB_BUF1, FB_BUF2 };

    if (low == nullptr)
    {
        printf("[SPN] low-res buffer alloc failed\r\n");
        return 6;
    }

    raster_surface_t rs;
    rs.w = RW;
    rs.h = RH;
    rs.stride = RW;
    rs.clip_x0 = 0;
    rs.clip_y0 = 0;
    rs.clip_x1 = RW - 1;
    rs.clip_y1 = RH - 1;

    /* divisor==1 直接画进目标缓冲；否则画进 low */
    rs.px = (divisor == 1) ? bufs[0] : low;

    for (int i = 0; i < 3; i++)
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
    }

    uint16_t *front = bufs[0];
    ltdc_set_framebuffer(front);

    /* 每块缓冲各自的上一帧脏矩形（渲染坐标系） */
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
    uint32_t raster_cycles = 0;
    uint32_t present_cycles = 0;

    int draw_idx = 1;

    for (int f = 0; f < total_frames; f++)
    {
        uint32_t f0 = DWT->CYCCNT;

        state.update(dt);
        state.apply(skeleton);
        skeleton.updateWorldTransform(spine::Physics_Update);

        uint16_t *dst = bufs[draw_idx];

        rs.px = (divisor == 1) ? dst : low;

        spine::RenderCommand *cmd_list = renderer.render(skeleton);

        int cbx0, cby0, cbx1, cby1;
        commands_bbox(cmd_list, scale, ox, oy, &cbx0, &cby0, &cbx1, &cby1);

        int dbx0 = (pbX[draw_idx] < 0) ? cbx0 : ((cbx0 < pbx[draw_idx]) ? cbx0 : pbx[draw_idx]);
        int dby0 = (pbX[draw_idx] < 0) ? cby0 : ((cby0 < pby[draw_idx]) ? cby0 : pby[draw_idx]);
        int dbx1 = (pbX[draw_idx] < 0) ? cbx1 : ((cbx1 > pbX[draw_idx]) ? cbx1 : pbX[draw_idx]);
        int dby1 = (pbX[draw_idx] < 0) ? cby1 : ((cby1 > pbY[draw_idx]) ? cby1 : pbY[draw_idx]);

        /* 夹到渲染区域 */
        if (dbx0 < 0) { dbx0 = 0; }
        if (dby0 < 0) { dby0 = 0; }
        if (dbx1 > RW - 1) { dbx1 = RW - 1; }
        if (dby1 > RH - 1) { dby1 = RH - 1; }

        uint32_t tc0 = DWT->CYCCNT;

        clear_rect(&rs, dbx0, dby0, dbx1, dby1, 0x0861u);

        uint32_t tc1 = DWT->CYCCNT;

        draw_commands(cmd_list, scale, ox, oy);

        uint32_t tc2 = DWT->CYCCNT;

        clear_cycles += tc1 - tc0;
        raster_cycles += tc2 - tc1;

        pbx[draw_idx] = cbx0;
        pby[draw_idx] = cby0;
        pbX[draw_idx] = cbx1;
        pbY[draw_idx] = cby1;

        if (divisor == 1)
        {
            raster_flush(dst, SCR_W * SCR_H * 2);
        }
        else
        {
            raster_flush(low, RW * RH * 2);

            /* 只放大脏矩形 */
            raster_upscale2x(low, RW, dst, SCR_W, dbx0, dby0, dbx1, dby1);
            raster_flush(dst + (size_t)(2 * dby0) * SCR_W, (dbx1 - dbx0 + 1) * 4 * (dby1 - dby0 + 1));
        }

        present_cycles += DWT->CYCCNT - tc2;

        while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
        {
        }

        ltdc_set_framebuffer(dst);

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

            printf("[SPN] t=%.1fs avg %.2f ms (%.1f fps) | clear %.2f raster %.2f present %.2f\r\n",
                   (float)(f + 1) / (float)fps, avg, 1000.0f / avg,
                   (float)clear_cycles / 480000.0f / (float)stat_frames,
                   (float)raster_cycles / 480000.0f / (float)stat_frames,
                   (float)present_cycles / 480000.0f / (float)stat_frames);

            stat_t0 = DWT->CYCCNT;
            stat_frames = 0;
            min_ms = 1e9f;
            max_ms = 0.0f;
            clear_cycles = 0;
            raster_cycles = 0;
            present_cycles = 0;
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

    if "divisor * divisor" in s:
        print("low-res playback already present")
        return

    marker = "/*----------------------------------------------------------------- 实时播放（三缓冲） */"
    i = s.find(marker)

    if i < 0:
        raise SystemExit("playback marker not found")

    s = s[:i].rstrip() + "\n\n" + FUNC.lstrip()
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("spine_play rewritten with divisor support")

    h = io.open(HEADER, encoding="utf-8").read()
    h = h.replace("uint8_t spine_play(const char *skel_path, const char *atlas_path, const char *anim, int fps, int seconds);",
                  "/* divisor: 1=全分辨率, 2=半分辨率(渲染 1/4 像素后 2x 放大) */\n"
                  "uint8_t spine_play(const char *skel_path, const char *atlas_path, const char *anim, int fps, int seconds, int divisor);")
    io.open(HEADER, "w", encoding="utf-8", newline="").write(h)

    c = io.open(SELFTEST, encoding="utf-8").read()
    c = c.replace('(void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 15);',
                  '(void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 4, 1);\n'
                  '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 10, 2);')
    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
    print("selftest: full-res then half-res runs")


if __name__ == "__main__":
    main()
