#!/usr/bin/env python3
"""Add a gravity-direction API and a physics demo.

spine 4.3 keeps gravity on the Skeleton (a global vector); every physics
constraint applies its own `gravity` magnitude along that vector.  So changing
the direction is:

    skeleton.setGravityX(gx);
    skeleton.setGravityY(gy);

The sample assets we have (celestial-circus / dragon / spineboy) ship with zero
physics constraints, so the demo injects one before constructing the Skeleton:
SkeletonData::getConstraints() is consulted by the Skeleton constructor, which
creates and registers the runtime constraint (and puts it into the update cache).

Run from the project root:  python DSH/middleware/patch_gravity.py
"""
import io

PATH = "User/spine_test.cpp"
HEADER = "User/spine_test.h"
SELFTEST = "User/selftest.c"

FUNC = r'''
/*----------------------------------------------------------------- 重力方向 + 物理形变 */

extern "C" void spine_set_gravity(spine::Skeleton *skel, float gx, float gy)
{
    if (skel != nullptr)
    {
        skel->setGravityX(gx);
        skel->setGravityY(gy);
    }
}

extern "C" void spine_dump_bones(spine::Skeleton *skel)
{
    spine::Array<spine::Bone *> &bones = skel->getBones();

    for (size_t i = 0; i < bones.size(); i++)
    {
        printf("        bone[%2d] %s\r\n", (int)i, bones[i]->getData().getName().buffer());
    }
}

/**
 * 物理重力演示：给指定骨骼注入一个物理约束，然后让重力方向绕一圈，
 * 观察该骨骼及其子链的形变。
 *
 * bone_name 为空时自动挑一个带子骨骼的骨骼。
 */
extern "C" uint8_t spine_gravity_test(const char *skel_path, const char *atlas_path,
                                      const char *anim, int fps, int seconds,
                                      int divisor, const char *bone_name)
{
    if (divisor < 1)
    {
        divisor = 1;
    }

    const int RW = SCR_W / divisor;
    const int RH = SCR_H / divisor;

    printf("\r\n[GRAV] gravity demo: %s | %d fps x %d s | render %dx%d\r\n",
           anim, fps, seconds, RW, RH);

    s_arena_used = 0;
    s_verts = (raster_vertex_t *)arena_alloc(sizeof(raster_vertex_t) * SPINE_MAX_VERTS);

    RawTextureLoader loader;
    spine::Atlas atlas(atlas_path, &loader);

    if (atlas.getPages().size() == 0)
    {
        printf("[GRAV] atlas load FAILED\r\n");
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
        printf("[GRAV] skeleton load FAILED\r\n");
        return 2;
    }

    /* ---- 选一根骨骼挂物理约束 ---- */
    spine::BoneData *target = nullptr;

    if ((bone_name != nullptr) && (bone_name[0] != '\0'))
    {
        target = sd->findBone(spine::String(bone_name));
    }

    if (target == nullptr)
    {
        spine::Array<spine::BoneData *> &bones = sd->getBones();

        for (size_t i = bones.size(); i > 0; i--)
        {
            spine::BoneData *b = bones[i - 1];

            if (b->getChildren().size() > 0)
            {
                target = b;
                break;
            }
        }
    }

    if (target == nullptr)
    {
        printf("[GRAV] no suitable bone\r\n");
        return 3;
    }

    printf("[GRAV] physics bone: %s (children %d)\r\n",
           target->getName().buffer(), (int)target->getChildren().size());

    /* ---- 注入物理约束数据（必须在 Skeleton 构造之前） ---- */
    spine::PhysicsConstraintData *pcd =
        new spine::PhysicsConstraintData(spine::String("demo-physics"));

    pcd->_bone = target;
    pcd->_limit = 5000.0f;
    pcd->_step = 1.0f / (float)fps;
    pcd->_setupPose.setInertia(0.5f);
    pcd->_setupPose.setStrength(100.0f);
    pcd->_setupPose.setDamping(0.85f);
    pcd->_setupPose.setMassInverse(1.0f);
    pcd->_setupPose.setGravity(1.0f);
    pcd->_setupPose.setMix(1.0f);

    sd->getConstraints().add(pcd);

    spine::Skeleton skeleton(*sd);

    printf("[GRAV] physics constraints in skeleton: %d\r\n",
           (int)skeleton.getPhysicsConstraints().size());

    spine::AnimationStateData asd(*sd);
    spine::AnimationState     state(asd);
    spine::SkeletonRenderer   renderer;

    skeleton.setupPose();
    skeleton.updateWorldTransform(spine::Physics_Setup);

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

    float sx = ((float)RW - 40.0f / (float)divisor) / (wmaxx - wminx);
    float sy = ((float)RH - 40.0f / (float)divisor) / (wmaxy - wminy);
    float scale = (sx < sy) ? sx : sy;
    float ox = ((float)RW - (wminx + wmaxx) * scale) * 0.5f;
    float oy = 20.0f / (float)divisor - wminy * scale;

    uint16_t *lows[3];
    uint16_t *bufs[3] = { (uint16_t *)FB_ADDR, FB_BUF1, FB_BUF2 };

    for (int i = 0; i < 3; i++)
    {
        lows[i] = (uint16_t *)arena_alloc((uint32_t)RW * RH * 2u);

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

    state.setAnimation(0, spine::String(anim), true);

    const float dt = 1.0f / (float)fps;
    int total_frames = fps * seconds;
    int draw_idx = 1;
    uint32_t t0 = HAL_GetTick();

    ltdc_set_framebuffer(bufs[0]);

    printf("[GRAV] sweeping gravity direction (2 turns over %d s)\r\n", seconds);

    for (int f = 0; f < total_frames; f++)
    {
        /* 重力方向绕一圈（2 圈 / 全程）：spine 的 y 轴向下，(0,1) = 向下 */
        float theta = 6.2831853f * 2.0f * (float)f / (float)total_frames;

        spine_set_gravity(&skeleton, cosf(theta), sinf(theta));

        state.update(dt);
        state.apply(skeleton);
        skeleton.updateWorldTransform(spine::Physics_Update);

        uint16_t *dst = bufs[draw_idx];
        rs.px = (divisor == 1) ? dst : lows[draw_idx];

        spine::RenderCommand *cmd = renderer.render(skeleton);

        int cbx0, cby0, cbx1, cby1;
        commands_bbox(cmd, scale, ox, oy, &cbx0, &cby0, &cbx1, &cby1);

        int dbx0 = (pbX[draw_idx] < 0) ? cbx0 : ((cbx0 < pbx[draw_idx]) ? cbx0 : pbx[draw_idx]);
        int dby0 = (pbX[draw_idx] < 0) ? cby0 : ((cby0 < pby[draw_idx]) ? cby0 : pby[draw_idx]);
        int dbx1 = (pbX[draw_idx] < 0) ? cbx1 : ((cbx1 > pbX[draw_idx]) ? cbx1 : pbX[draw_idx]);
        int dby1 = (pbX[draw_idx] < 0) ? cby1 : ((cby1 > pbY[draw_idx]) ? cby1 : pbY[draw_idx]);

        if (dbx0 < 0) { dbx0 = 0; }
        if (dby0 < 0) { dby0 = 0; }
        if (dbx1 > RW - 1) { dbx1 = RW - 1; }
        if (dby1 > RH - 1) { dby1 = RH - 1; }

        clear_rect(&rs, dbx0, dby0, dbx1, dby1, 0x0861u);
        draw_commands(cmd, scale, ox, oy, &rs);

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

        while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
        {
        }

        ltdc_set_framebuffer(dst);
        draw_idx = (draw_idx + 1) % 3;
    }

    float ms = (float)(HAL_GetTick() - t0) / (float)total_frames;

    printf("[GRAV] %.2f ms/frame (%.1f fps)\r\n", ms, 1000.0f / ms);
    printf("[GRAV] RESULT PASS\r\n");
    return 0;
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "spine_gravity_test" in s:
        print("gravity demo already present")
        return

    s = s.rstrip() + "\n" + FUNC
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)

    h = io.open(HEADER, encoding="utf-8").read()
    h = h.replace("uint8_t spine_play_duo(const char *skel_path, const char *atlas_path,",
                  "/* 设置骨架的全局重力方向（作用于所有物理约束） */\n"
                  "void spine_set_gravity(spine::Skeleton *skel, float gx, float gy);\n\n"
                  "/* 物理重力演示：给骨骼注入物理约束并旋转重力方向 */\n"
                  "uint8_t spine_gravity_test(const char *skel_path, const char *atlas_path,\n"
                  "                           const char *anim, int fps, int seconds,\n"
                  "                           int divisor, const char *bone_name);\n\n"
                  "uint8_t spine_play_duo(const char *skel_path, const char *atlas_path,", 1)
    io.open(HEADER, "w", encoding="utf-8", newline="").write(h)

    c = io.open(SELFTEST, encoding="utf-8").read()
    old = '    /* 双角色实测（你的素材）：swing + wing-flap，全分辨率 2 轮 */'
    new = ('    /* 重力方向演示：给 hair-back 注入物理约束，重力绕圈 */\n'
           '    (void)spine_gravity_test("/spine/celestial-circus-pro.skel",\n'
           '                             "/spine/celestial-circus-pro.atlas",\n'
           '                             "wind-idle", 60, 8, 1, "hair-back");\n\n'
           '    /* 双角色实测（你的素材）：swing + wing-flap，全分辨率 2 轮 */')
    if old in c:
        c = c.replace(old, new, 1)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("selftest: gravity demo wired")
    else:
        print("WARNING: selftest anchor not found")


if __name__ == "__main__":
    main()
