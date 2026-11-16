#!/usr/bin/env python3
"""Append an animation contact-sheet renderer to User/spine_test.cpp.

Renders every animation of a skeleton at a fixed time into a grid of cells, so a
single framebuffer dump shows all clips at once.  Also prints the clip names and
the total render time.

Run from the project root:  python DSH/middleware/patch_spine_sheet.py
"""
import io

PATH = "User/spine_test.cpp"

FUNC = r'''
/*----------------------------------------------------------------- 动画总览 */

extern "C" uint8_t spine_anim_sheet(const char *skel_path, const char *atlas_path, float at_time)
{
    printf("\r\n[SPN] animation contact sheet\r\n");

    s_surf.px = (uint16_t *)FB_ADDR;
    s_surf.w = SCR_W;
    s_surf.h = SCR_H;
    s_surf.stride = SCR_W;
    s_surf.clip_x0 = 0;
    s_surf.clip_y0 = 0;
    s_surf.clip_x1 = SCR_W - 1;
    s_surf.clip_y1 = SCR_H - 1;

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

    spine::Skeleton         skeleton(*sd);
    spine::AnimationStateData asd(*sd);
    spine::AnimationState   state(asd);
    spine::SkeletonRenderer renderer;

    /* 动画名列表 */
    size_t n_anim = sd->getAnimations().size();

    printf("[SPN] %d animations:\r\n", (int)n_anim);

    for (size_t i = 0; i < n_anim; i++)
    {
        printf("        [%2d] %s\r\n", (int)i, sd->getAnimations()[i]->getName().buffer());
    }

    /* 包围盒（setup pose） */
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

    const int cols = 4;
    const int rows = 3;
    const float cell_w = (float)SCR_W / cols;
    const float cell_h = (float)SCR_H / rows;

    float cell_scale = (cell_h - 26.0f) / (wmaxy - wminy);

    raster_clear(&s_surf, 0x1082u);

    uint32_t t0 = DWT->CYCCNT;

    for (size_t i = 0; (i < n_anim) && (i < (size_t)(cols * rows)); i++)
    {
        int cx = (int)(i % cols);
        int cy = (int)(i / cols);

        float ox = cx * cell_w + (cell_w - (wmaxx - wminx) * cell_scale) * 0.5f - wminx * cell_scale;
        float oy = cy * cell_h + 14.0f - wminy * cell_scale;

        skeleton.setupPose();
        state.clearTracks();
        state.setAnimation(0, sd->getAnimations()[i]->getName(), true);
        state.update(at_time);
        state.apply(skeleton);
        skeleton.updateWorldTransform(spine::Physics_Update);

        spine::RenderCommand *cmd = renderer.render(skeleton);

        draw_commands(cmd, cell_scale, ox, oy);

        /* 名字 */
        g_back_color = 0x1082u;
        lcd_show_string((uint16_t)(cx * cell_w + 6), (uint16_t)(cy * cell_h + cell_h - 18),
                        (uint16_t)(cell_w - 10), 16, 16,
                        (char *)sd->getAnimations()[i]->getName().buffer(), 0xFFFFu);
    }

    uint32_t cycles = DWT->CYCCNT - t0;

    raster_flush((uint16_t *)FB_ADDR, SCR_W * SCR_H * 2);

    float ms = (float)cycles / 480000.0f;

    printf("[SPN] sheet: %d cells rendered in %.2f ms (%.1f fps for whole sheet)\r\n",
           (int)((n_anim < (size_t)(cols * rows)) ? n_anim : (size_t)(cols * rows)),
           ms, (ms > 0.0f) ? (1000.0f / ms) : 0.0f);

    printf("[SPN] RESULT PASS\r\n");
    return 0;
}
'''

SELFTEST = "User/selftest.c"
CALL_OLD = '    (void)spine_test_run("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "run", 30);'
CALL_NEW = ('    (void)spine_anim_sheet("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", 0.45f);')


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "spine_anim_sheet" in s:
        print("sheet function already present")
    else:
        s = s.rstrip() + "\n" + FUNC
        io.open(PATH, "w", encoding="utf-8", newline="").write(s)
        print("sheet function appended")

    h = io.open("User/spine_test.h", encoding="utf-8").read()

    if "spine_anim_sheet" not in h:
        h = h.replace("uint8_t spine_test_run(const char *skel_path, const char *atlas_path, const char *anim, int frames);",
                      "uint8_t spine_test_run(const char *skel_path, const char *atlas_path, const char *anim, int frames);\n\n"
                      "/* 渲染所有动画的总览网格（一帧一图） */\n"
                      "uint8_t spine_anim_sheet(const char *skel_path, const char *atlas_path, float at_time);")
        io.open("User/spine_test.h", "w", encoding="utf-8", newline="").write(h)
        print("header updated")

    c = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_anim_sheet" not in c:
        c = c.replace(CALL_OLD, CALL_NEW)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("selftest call switched to sheet")


if __name__ == "__main__":
    main()
