#!/usr/bin/env python3
"""Append a real-time animation playback loop (double buffered) to spine_test.cpp.

Renders the requested clip continuously at a fixed frame rate, swapping two
framebuffers on the LTDC vertical blank so the animation is tear-free.  Prints
frame-time statistics every second.

Run from the project root:  python DSH/middleware/patch_spine_play.py
"""
import io

PATH = "User/spine_test.cpp"
HEADER = "User/spine_test.h"
SELFTEST = "User/selftest.c"

FUNC = r'''
/*----------------------------------------------------------------- 实时播放 */

#define FB_BACK ((uint16_t *)0xC1A00000u)      /* 第二块帧缓冲（SDRAM 尾部，不与堆/arena 冲突） */

static void ltdc_set_framebuffer(uint16_t *addr)
{
    LTDC_Layer1->CFBAR = (uint32_t)addr;
    LTDC->SRCR = LTDC_SRCR_VBR;                /* 垂直回扫时生效，避免撕裂 */
}

extern "C" uint8_t spine_play(const char *skel_path, const char *atlas_path,
                              const char *anim, int fps, int seconds)
{
    printf("\r\n[SPN] realtime playback: %s @ %d fps for %d s\r\n", anim, fps, seconds);

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

    /* 包围盒（setup pose）→ 全屏适配 */
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

    /* 双缓冲 */
    uint16_t *front = (uint16_t *)FB_ADDR;
    uint16_t *back = FB_BACK;

    ltdc_set_framebuffer(front);

    s_surf.px = back;
    s_surf.w = SCR_W;
    s_surf.h = SCR_H;
    s_surf.stride = SCR_W;
    s_surf.clip_x0 = 0;
    s_surf.clip_y0 = 0;
    s_surf.clip_x1 = SCR_W - 1;
    s_surf.clip_y1 = SCR_H - 1;

    state.setAnimation(0, spine::String(anim), true);

    const float dt = 1.0f / (float)fps;
    int total_frames = fps * seconds;
    uint32_t stat_t0 = DWT->CYCCNT;
    int stat_frames = 0;
    float min_ms = 1e9f, max_ms = 0.0f;

    for (int f = 0; f < total_frames; f++)
    {
        uint32_t f0 = DWT->CYCCNT;

        state.update(dt);
        state.apply(skeleton);
        skeleton.updateWorldTransform(spine::Physics_Update);

        raster_clear(&s_surf, 0x0861u);
        draw_commands(renderer.render(skeleton), scale, ox, oy);

        raster_flush(s_surf.px, SCR_W * SCR_H * 2);

        /* 交换：刚画好的这块变成前台，下一帧画另一块 */
        ltdc_set_framebuffer(s_surf.px);

        uint16_t *tmp = front;
        front = back;
        back = tmp;
        s_surf.px = back;

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

            printf("[SPN] t=%.1fs  avg %.2f ms  min %.2f  max %.2f  (%.1f fps)\r\n",
                   (float)(f + 1) / (float)fps, avg, min_ms, max_ms, 1000.0f / avg);

            stat_t0 = DWT->CYCCNT;
            stat_frames = 0;
            min_ms = 1e9f;
            max_ms = 0.0f;
        }
    }

    /* 恢复到前台缓冲 A，保证后续 LCD 文字写在同一块上 */
    ltdc_set_framebuffer((uint16_t *)FB_ADDR);

    printf("[SPN] playback done (%d frames)\r\n", total_frames);
    printf("[SPN] RESULT PASS\r\n");
    return 0;
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "spine_play" in s:
        print("playback already present")
    else:
        s = s.rstrip() + "\n" + FUNC
        io.open(PATH, "w", encoding="utf-8", newline="").write(s)
        print("playback appended")

    h = io.open(HEADER, encoding="utf-8").read()

    if "spine_play" not in h:
        h = h.replace("uint8_t spine_anim_sheet(const char *skel_path, const char *atlas_path, float at_time);",
                      "uint8_t spine_anim_sheet(const char *skel_path, const char *atlas_path, float at_time);\n\n"
                      "/* 实时循环播放指定动画（双缓冲，framerate 由 fps 决定） */\n"
                      "uint8_t spine_play(const char *skel_path, const char *atlas_path, const char *anim, int fps, int seconds);")
        io.open(HEADER, "w", encoding="utf-8", newline="").write(h)
        print("header updated")

    c = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_play" not in c:
        old = '    (void)spine_anim_sheet("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", 0.45f);'
        new = (old + "\n\n"
               '    /* ---- walk 动画实时播放（双缓冲，30fps，20 秒）---- */\n'
               '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 30, 20);')
        c = c.replace(old, new)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("selftest call added")


if __name__ == "__main__":
    main()
