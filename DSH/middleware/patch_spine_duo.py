#!/usr/bin/env python3
"""Add spine_play_duo(): two skeletons with different animations, reloaded from
file on every iteration, full-res or half-res, with per-iteration fps and spine
heap statistics (to detect leaks across reloads).

Run from the project root:  python DSH/middleware/patch_spine_duo.py
"""
import io

PATH = "User/spine_test.cpp"
HEADER = "User/spine_test.h"
SELFTEST = "User/selftest.c"

FUNC = r'''
/*----------------------------------------------------------------- 双角色 + 反复重载 */

struct DuoChar
{
    spine::Skeleton       *skel;
    spine::AnimationState *state;
    float scale, ox, oy;
};

static void duo_fit(DuoChar *c, float wminx, float wmaxx, float wminy, float wmaxy,
                    float cell_x, float cell_w, float rw, float rh)
{
    float sx = (cell_w - 20.0f) / (wmaxx - wminx);
    float sy = (rh - 30.0f) / (wmaxy - wminy);
    float s = (sx < sy) ? sx : sy;

    c->scale = s;
    c->ox = cell_x + (cell_w - (wmaxx - wminx) * s) * 0.5f - wminx * s;
    c->oy = 15.0f - wminy * s;
}

extern "C" uint8_t spine_play_duo(const char *skel_path, const char *atlas_path,
                                  const char *anim_a, const char *anim_b,
                                  int fps, int seconds, int divisor, int iterations)
{
    if (divisor < 1)
    {
        divisor = 1;
    }

    const int RW = SCR_W / divisor;
    const int RH = SCR_H / divisor;

    printf("\r\n[DUO] 2 characters, render %dx%d, %d fps, %d s x %d iters\r\n",
           RW, RH, fps, seconds, iterations);

    uint16_t *bufs[3] = { (uint16_t *)FB_ADDR, FB_BUF1, FB_BUF2 };
    uint16_t *lows[3] = { nullptr, nullptr, nullptr };

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

    float total_ms[8];

    for (int it = 0; it < iterations && it < 8; it++)
    {
        uint32_t t_load0 = DWT->CYCCNT;

        /* 每次迭代都重新从文件加载 */
        s_arena_used = 0;
        s_verts = (raster_vertex_t *)arena_alloc(sizeof(raster_vertex_t) * SPINE_MAX_VERTS);

        for (int i = 0; i < 3; i++)
        {
            lows[i] = (uint16_t *)arena_alloc((uint32_t)RW * RH * 2u);
        }

        if ((s_verts == nullptr) || (lows[0] == nullptr) || (lows[1] == nullptr) || (lows[2] == nullptr))
        {
            printf("[DUO] arena alloc failed\r\n");
            return 6;
        }

        RawTextureLoader loader;
        spine::Atlas atlas(atlas_path, &loader);

        if (atlas.getPages().size() == 0)
        {
            printf("[DUO] atlas load FAILED\r\n");
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
            printf("[DUO] skeleton load FAILED\r\n");
            return 2;
        }

        uint32_t load_cycles = DWT->CYCCNT - t_load0;
        float    load_ms = (float)load_cycles / 480000.0f;

        spine_heap_stats_t hs0;
        spine_heap_get_stats(&hs0);

        /* 两个独立 skeleton，播不同动画 */
        spine::Skeleton *skA = new spine::Skeleton(*sd);
        spine::Skeleton *skB = new spine::Skeleton(*sd);

        spine::AnimationStateData asdA(*sd);
        spine::AnimationStateData asdB(*sd);
        spine::AnimationState *stA = new spine::AnimationState(asdA);
        spine::AnimationState *stB = new spine::AnimationState(asdB);

        skA->setupPose();
        skA->updateWorldTransform(spine::Physics_Update);
        skB->setupPose();
        skB->updateWorldTransform(spine::Physics_Update);

        float wminx = 1e9f, wmaxx = -1e9f, wminy = 1e9f, wmaxy = -1e9f;
        {
            spine::SkeletonRenderer probe;
            spine::RenderCommand *m = probe.render(*skA);

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

        DuoChar A = { skA, stA, 1.0f, 0.0f, 0.0f };
        DuoChar B = { skB, stB, 1.0f, 0.0f, 0.0f };

        duo_fit(&A, wminx, wmaxx, wminy, wmaxy, 0.0f, (float)RW * 0.5f, (float)RW, (float)RH);
        duo_fit(&B, wminx, wmaxx, wminy, wmaxy, (float)RW * 0.5f, (float)RW * 0.5f, (float)RW, (float)RH);

        stA->setAnimation(0, spine::String(anim_a), true);
        stB->setAnimation(0, spine::String(anim_b), true);

        spine::SkeletonRenderer rA, rB;

        raster_surface_t rs;
        rs.w = RW;
        rs.h = RH;
        rs.stride = RW;
        rs.clip_x0 = 0;
        rs.clip_y0 = 0;
        rs.clip_x1 = RW - 1;
        rs.clip_y1 = RH - 1;
        rs.px = lows[0];

        for (int i = 0; i < 3; i++)
        {
            rs.px = lows[i];
            raster_clear(&rs, 0x0861u);
            raster_flush(lows[i], RW * RH * 2);
        }

        int pbx[3], pby[3], pbX[3], pbY[3];

        for (int i = 0; i < 3; i++)
        {
            pbx[i] = 0; pby[i] = 0; pbX[i] = -1; pbY[i] = -1;
        }

        const float dt = 1.0f / (float)fps;
        int total_frames = fps * seconds;
        int draw_idx = 1;
        uint32_t fr0 = DWT->CYCCNT;
        uint32_t clr_cyc = 0, ras_cyc = 0, pre_cyc = 0;

        ltdc_set_framebuffer(bufs[0]);

        for (int f = 0; f < total_frames; f++)
        {
            stA->update(dt);
            stA->apply(*skA);
            skA->updateWorldTransform(spine::Physics_Update);

            stB->update(dt);
            stB->apply(*skB);
            skB->updateWorldTransform(spine::Physics_Update);

            uint16_t *dst = bufs[draw_idx];
            rs.px = (divisor == 1) ? dst : lows[draw_idx];

            spine::RenderCommand *cA = rA.render(*skA);
            spine::RenderCommand *cB = rB.render(*skB);

            int ax0, ay0, ax1, ay1;
            int bx0, by0, bx1, by1;

            commands_bbox(cA, A.scale, A.ox, A.oy, &ax0, &ay0, &ax1, &ay1);
            commands_bbox(cB, B.scale, B.ox, B.oy, &bx0, &by0, &bx1, &by1);

            int cbx0 = (ax0 < bx0) ? ax0 : bx0;
            int cby0 = (ay0 < by0) ? ay0 : by0;
            int cbx1 = (ax1 > bx1) ? ax1 : bx1;
            int cby1 = (ay1 > by1) ? ay1 : by1;

            int dbx0 = (pbX[draw_idx] < 0) ? cbx0 : ((cbx0 < pbx[draw_idx]) ? cbx0 : pbx[draw_idx]);
            int dby0 = (pbX[draw_idx] < 0) ? cby0 : ((cby0 < pby[draw_idx]) ? cby0 : pby[draw_idx]);
            int dbx1 = (pbX[draw_idx] < 0) ? cbx1 : ((cbx1 > pbX[draw_idx]) ? cbx1 : pbX[draw_idx]);
            int dby1 = (pbX[draw_idx] < 0) ? cby1 : ((cby1 > pbY[draw_idx]) ? cby1 : pbY[draw_idx]);

            if (dbx0 < 0) { dbx0 = 0; }
            if (dby0 < 0) { dby0 = 0; }
            if (dbx1 > RW - 1) { dbx1 = RW - 1; }
            if (dby1 > RH - 1) { dby1 = RH - 1; }

            uint32_t c0 = DWT->CYCCNT;
            clear_rect(&rs, dbx0, dby0, dbx1, dby1, 0x0861u);
            uint32_t c1 = DWT->CYCCNT;

            draw_commands(cA, A.scale, A.ox, A.oy, &rs);
            draw_commands(cB, B.scale, B.ox, B.oy, &rs);
            uint32_t c2 = DWT->CYCCNT;

            clr_cyc += c1 - c0;
            ras_cyc += c2 - c1;

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
                raster_flush(lows[draw_idx], RW * RH * 2);
                raster_upscale2x(lows[draw_idx], RW, dst, SCR_W, dbx0, dby0, dbx1, dby1);
                raster_flush(dst + (size_t)(2 * dby0) * SCR_W,
                             (dbx1 - dbx0 + 1) * 4 * (dby1 - dby0 + 1) * 2);
            }

            pre_cyc += DWT->CYCCNT - c2;

            while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
            {
            }

            ltdc_set_framebuffer(dst);
            draw_idx = (draw_idx + 1) % 3;
        }

        float frame_ms = (float)(DWT->CYCCNT - fr0) / 480000.0f / (float)total_frames;
        total_ms[it] = frame_ms;

        spine_heap_stats_t hs1;
        spine_heap_get_stats(&hs1);

        printf("[DUO] it%d load %.1f ms | %.2f ms/frame (%.1f fps) | clear %.2f raster %.2f present %.2f | heap %lu->%lu peak %lu fails %lu\r\n",
               it + 1, load_ms, frame_ms, 1000.0f / frame_ms,
               (float)clr_cyc / 480000.0f / (float)total_frames,
               (float)ras_cyc / 480000.0f / (float)total_frames,
               (float)pre_cyc / 480000.0f / (float)total_frames,
               (unsigned long)hs0.used_bytes, (unsigned long)hs1.used_bytes,
               (unsigned long)hs1.peak_bytes, (unsigned long)hs1.fail_count);

        delete stA;
        delete stB;
        delete skA;
        delete skB;

        spine_heap_stats_t hs2;
        spine_heap_get_stats(&hs2);

        printf("[DUO] it%d after delete: heap used %lu (delta after load %ld)\r\n",
               it + 1, (unsigned long)hs2.used_bytes,
               (long)hs2.used_bytes - (long)hs0.used_bytes);
    }

    ltdc_set_framebuffer(bufs[0]);

    printf("[DUO] ================================\r\n");
    printf("[DUO] fps per iteration:\r\n");

    for (int it = 0; it < iterations && it < 8; it++)
    {
        printf("[DUO]   it%d: %.1f fps (%.2f ms)\r\n", it + 1, 1000.0f / total_ms[it], total_ms[it]);
    }

    printf("[DUO] RESULT PASS\r\n");
    return 0;
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "spine_play_duo" in s:
        print("duo already present")
        return

    s = s.rstrip() + "\n" + FUNC
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)

    h = io.open(HEADER, encoding="utf-8").read()
    h = h.replace("uint8_t spine_play(const char *skel_path, const char *atlas_path, const char *anim, int fps, int seconds, int divisor);",
                  "uint8_t spine_play(const char *skel_path, const char *atlas_path, const char *anim, int fps, int seconds, int divisor);\n\n"
                  "/* 双角色（不同动画）+ 每次迭代重新从文件加载，用于负载与泄漏测试 */\n"
                  "uint8_t spine_play_duo(const char *skel_path, const char *atlas_path,\n"
                  "                       const char *anim_a, const char *anim_b,\n"
                  "                       int fps, int seconds, int divisor, int iterations);")
    io.open(HEADER, "w", encoding="utf-8", newline="").write(h)

    c = io.open(SELFTEST, encoding="utf-8").read()
    old = ('    /* 全分辨率基准 4s + 半分辨率播放 12s */\n'
           '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 4, 1);\n'
           '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 12, 2);')
    new = ('    /* 双角色实验：全分辨率 3 轮 + 半分辨率 3 轮 */\n'
           '    (void)spine_play_duo("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas",\n'
           '                         "walk", "run", 60, 4, 1, 3);\n'
           '    (void)spine_play_duo("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas",\n'
           '                         "walk", "run", 60, 4, 2, 3);')
    if old in c:
        c = c.replace(old, new, 1)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("selftest: duo experiment wired")
    else:
        print("WARNING: selftest call pattern not found")


if __name__ == "__main__":
    main()
