/**
 ****************************************************************************************************
 * @file        spine_api.cpp
 * @brief       Spine 运行时对外 API 实现（资产 / 实例 / 每帧绘制）
 *
 * 分层：
 *   spine_api.cpp    ← 本文件：面向游戏的实例与绘制调度
 *   spine_platform   ← 分配器、纹理加载、FatFs
 *   raster2d         ← 扫描线光栅器（与平台无关）
 *   spine-cpp        ← 动画/骨架/物理
 ****************************************************************************************************
 */

#include "spine_api.h"
#include "spine_platform.h"
#include "plat/plat.h"

extern "C"
{
#include "./SYSTEM/sys/sys.h"
#include "./BSP/LCD/lcd.h"
#include "./RASTER/raster2d.h"
}

#include <spine/Atlas.h>
#include <spine/AtlasAttachmentLoader.h>
#include <spine/SkeletonBinary.h>
#include <spine/SkeletonData.h>
#include <spine/Skeleton.h>
#include <spine/Animation.h>
#include <spine/AnimationState.h>
#include <spine/AnimationStateData.h>
#include <spine/SkeletonRenderer.h>
#include <spine/Bone.h>
#include <spine/PhysicsConstraint.h>

#include <string.h>
#include <stdio.h>

/*----------------------------------------------------------------- 常量 */

#define SPINE_SCR_W     800
#define SPINE_SCR_H     480
#define SPINE_FB0       ((uint16_t *)0xC0000000u)
#define SPINE_FB1       ((uint16_t *)0xC1A00000u)
#define SPINE_FB2       ((uint16_t *)0xC1B00000u)
#define SPINE_BG        0x0861u
#define SPINE_MAX_INST  32
#define SPINE_MAX_VERTS 8192

/* 由应用层（fb_mpu_set）设置：帧缓冲是否写穿缓存 */



/*----------------------------------------------------------------- 数据结构 */

struct spine_asset
{
    RawTextureLoader             *loader;
    spine::Atlas                 *atlas;
    spine::AtlasAttachmentLoader *attachment_loader;
    spine::SkeletonBinary        *binary;
    spine::SkeletonData          *data;
};

struct spine_instance
{
    spine_asset_t        *asset;
    spine::Skeleton      *skel;
    spine::AnimationStateData *asd;
    spine::AnimationState     *state;
    spine::SkeletonRenderer   *renderer;
    spine::RenderCommand      *cmds;       /* 最近一次 render 的结果 */
    spine::TrackEntry         *tracks[4];  /* 每条轨道当前的 TrackEntry */

    float    x, y;                          /* 世界原点在屏幕上的位置 */
    float    scale;
    float    flip_x, flip_y;
    uint32_t tint;                          /* RGBA8888 */
    uint8_t  alpha;
};

/*----------------------------------------------------------------- 绘制状态 */

static struct
{
    int      inited;
    int      divisor;
    float    inv_divisor;
    int      rw, rh;
    uint16_t *lows[3];
    uint16_t *bufs[3];
    int      draw_idx;
    int      pbx[3], pby[3], pbX[3], pbY[3];

    raster_surface_t surf;
    raster_vertex_t *verts;

    spine_instance_t *queue[SPINE_MAX_INST];
    int      qcount;

    int      have_bbox;
    int      fbx0, fby0, fbx1, fby1;
} g_d;

/*----------------------------------------------------------------- 世界重力 */

static float             g_gx = 0.0f;
static float             g_gy = 1.0f;
static spine_instance_t *g_reg[SPINE_MAX_INST];
static int               g_reg_count = 0;

/*----------------------------------------------------------------- 工具 */

static void api_set_framebuffer(uint16_t *addr)
{
    plat_fb_present(addr);
}

static inline void api_xform(const spine_instance_t *in, float wx, float wy, float *sx, float *sy)
{
    *sx = wx * in->scale * in->flip_x + in->x;
    *sy = wy * in->scale * in->flip_y + in->y;
}

static inline uint32_t mul_color(uint32_t c, uint32_t t)
{
    uint32_t a = (((c >> 24) & 0xFFu) * ((t >> 24) & 0xFFu)) / 255u;
    uint32_t r = (((c >> 16) & 0xFFu) * ((t >> 16) & 0xFFu)) / 255u;
    uint32_t g = (((c >> 8) & 0xFFu) * ((t >> 8) & 0xFFu)) / 255u;
    uint32_t b = ((c & 0xFFu) * (t & 0xFFu)) / 255u;

    return (a << 24) | (r << 16) | (g << 8) | b;
}

static void fill_rect(raster_surface_t *s, int x0, int y0, int x1, int y1, uint16_t color)
{
    if (x0 < s->clip_x0) { x0 = s->clip_x0; }
    if (y0 < s->clip_y0) { y0 = s->clip_y0; }
    if (x1 > s->clip_x1) { x1 = s->clip_x1; }
    if (y1 > s->clip_y1) { y1 = s->clip_y1; }

    if ((x0 > x1) || (y0 > y1))
    {
        return;
    }

    for (int y = y0; y <= y1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        for (int x = x0; x <= x1; x++)
        {
            row[x] = color;
        }
    }
}

/*----------------------------------------------------------------- 资产 */

spine_asset_t *spine_asset_load(const char *skel_path, const char *atlas_path)
{

    spine_asset_t *a = (spine_asset_t *)spine_heap_alloc((size_t)sizeof(spine_asset_t));

    if (a == nullptr)
    {
        printf("[API] asset alloc failed\r\n");
        return nullptr;
    }

    memset(a, 0, sizeof(*a));

    a->loader = new RawTextureLoader();
    a->atlas = new spine::Atlas(spine::String(atlas_path), a->loader);


    if (a->atlas->getPages().size() == 0)
    {
        printf("[API] atlas load FAILED: %s\r\n", atlas_path);
        spine_asset_free(a);
        return nullptr;
    }

    for (size_t i = 0; i < a->atlas->getRegions().size(); i++)
    {
        spine::AtlasRegion *r = a->atlas->getRegions()[i];

        if (r->getPage() != nullptr)
        {
            r->setRendererObject(r->getPage()->texture);
        }
    }

    a->attachment_loader = new spine::AtlasAttachmentLoader(*a->atlas);
    a->binary = new spine::SkeletonBinary(*a->attachment_loader, false);
    a->data = a->binary->readSkeletonDataFile(skel_path);

    if (a->data == nullptr)
    {
        printf("[API] skeleton load FAILED: %s\r\n", skel_path);
        spine_asset_free(a);
        return nullptr;
    }

    printf("[API] asset loaded: %s | %d animations | %d textures\r\n",
           skel_path,
           (int)a->data->getAnimations().size(),
           (int)a->atlas->getPages().size());

    return a;
}

void spine_asset_free(spine_asset_t *a)
{
    if (a == nullptr)
    {
        return;
    }

    delete a->data;
    delete a->binary;
    delete a->attachment_loader;
    delete a->atlas;
    delete a->loader;

    spine_heap_free(a);
}

int spine_asset_anim_count(spine_asset_t *a)
{
    return (a != nullptr) ? (int)a->data->getAnimations().size() : 0;
}

const char *spine_asset_anim_name(spine_asset_t *a, int index)
{
    if ((a == nullptr) || (index < 0) || (index >= (int)a->data->getAnimations().size()))
    {
        return nullptr;
    }

    return a->data->getAnimations()[index]->getName().buffer();
}

uint32_t spine_asset_texture_bytes(spine_asset_t *a)
{
    uint32_t total = 0;

    if (a == nullptr)
    {
        return 0;
    }

    spine::Array<spine::AtlasPage *> &pages = a->atlas->getPages();

    for (size_t i = 0; i < pages.size(); i++)
    {
        const RawTexture *t = (const RawTexture *)pages[i]->texture;

        if (t != nullptr)
        {
            total += (uint32_t)t->w * t->h * 2u;
        }
    }

    return total;
}

/*----------------------------------------------------------------- 实例 */

spine_instance_t *spine_instance_create(spine_asset_t *a)
{
    if (a == nullptr)
    {
        return nullptr;
    }

    spine_instance_t *in = (spine_instance_t *)spine_heap_alloc((size_t)sizeof(spine_instance_t));

    if (in == nullptr)
    {
        return nullptr;
    }

    memset(in, 0, sizeof(*in));

    in->asset = a;
    in->skel = new spine::Skeleton(*a->data);
    in->asd = new spine::AnimationStateData(*a->data);
    in->state = new spine::AnimationState(*in->asd);
    in->renderer = new spine::SkeletonRenderer();

    in->x = 0.0f;
    in->y = 0.0f;
    in->scale = 1.0f;
    in->flip_x = 1.0f;
    in->flip_y = 1.0f;
    in->tint = 0xFFFFFFFFu;
    in->alpha = 255;

    in->skel->setupPose();
    in->skel->updateWorldTransform(spine::Physics_Update);

    /* 自动注册到世界重力 */
    if (g_reg_count < SPINE_MAX_INST)
    {
        in->skel->setGravityX(g_gx);
        in->skel->setGravityY(g_gy);
        g_reg[g_reg_count++] = in;
    }

    return in;
}

void spine_instance_destroy(spine_instance_t *in)
{
    if (in == nullptr)
    {
        return;
    }

    for (int i = 0; i < g_reg_count; i++)
    {
        if (g_reg[i] == in)
        {
            for (int j = i; j < (g_reg_count - 1); j++)
            {
                g_reg[j] = g_reg[j + 1];
            }
            g_reg_count--;
            g_reg[g_reg_count] = nullptr;
            break;
        }
    }

    delete in->renderer;
    delete in->state;
    delete in->asd;
    delete in->skel;

    spine_heap_free(in);
}

/*----------------------------------------------------------------- 动画控制 */

void spine_instance_play(spine_instance_t *in, const char *anim, int loop, int track)
{
    if ((in == nullptr) || (anim == nullptr) || (anim[0] == 0))
    {
        return;
    }

    if ((track < 0) || (track >= 4))
    {
        return;
    }

    in->tracks[track] = &in->state->setAnimation((size_t)track, spine::String(anim), (loop != 0));
}

void spine_instance_stop(spine_instance_t *in, int track)
{
    if ((in != nullptr) && (track >= 0) && (track < 4))
    {
        in->state->clearTrack((size_t)track);
        in->tracks[track] = nullptr;
    }
}

void spine_instance_set_speed(spine_instance_t *in, float speed, int track)
{
    if (in == nullptr)
    {
        return;
    }

    if ((track >= 0) && (track < 4) && (in->tracks[track] != nullptr))
    {
        in->tracks[track]->setTimeScale(speed);
    }
}

void spine_instance_set_time(spine_instance_t *in, float seconds, int track)
{
    if (in == nullptr)
    {
        return;
    }

    if ((track >= 0) && (track < 4) && (in->tracks[track] != nullptr))
    {
        in->tracks[track]->setTrackTime(seconds);
        in->tracks[track]->setTimeScale(0.0f);      /* 停在指定时间 */
    }
}

/*----------------------------------------------------------------- 变换与外观 */

void spine_instance_set_position(spine_instance_t *in, float x, float y)
{
    if (in != nullptr) { in->x = x; in->y = y; }
}

void spine_instance_set_scale(spine_instance_t *in, float scale)
{
    if (in != nullptr) { in->scale = scale; }
}

void spine_instance_set_flip(spine_instance_t *in, int flip_x, int flip_y)
{
    if (in != nullptr)
    {
        in->flip_x = (flip_x != 0) ? -1.0f : 1.0f;
        in->flip_y = (flip_y != 0) ? -1.0f : 1.0f;
    }
}

void spine_instance_set_tint(spine_instance_t *in, uint32_t rgba8888)
{
    if (in != nullptr) { in->tint = rgba8888; }
}

void spine_instance_set_alpha(spine_instance_t *in, uint8_t alpha)
{
    if (in != nullptr) { in->alpha = alpha; }
}

/*----------------------------------------------------------------- 每帧更新 */

void spine_instance_update(spine_instance_t *in, float dt)
{
    if ((in == nullptr) || (in->skel == nullptr))
    {
        return;
    }

    in->state->update(dt);
    in->state->apply(*in->skel);

    /* 推进骨架时间：物理约束的步进量来自 _time 的增量 */
    in->skel->update(dt);
    in->skel->updateWorldTransform(spine::Physics_Update);

    in->cmds = in->renderer->render(*in->skel);
}

int spine_instance_get_bounds(spine_instance_t *in, float *x0, float *y0, float *x1, float *y1)
{
    if (in == nullptr)
    {
        return 0;
    }

    if (in->cmds == nullptr)
    {
        in->cmds = in->renderer->render(*in->skel);
    }

    float minx = 1e9f, maxx = -1e9f, miny = 1e9f, maxy = -1e9f;

    for (spine::RenderCommand *c = in->cmds; c != nullptr; c = c->next)
    {
        for (int i = 0; i < c->numVertices; i++)
        {
            float sx, sy;

            api_xform(in, c->positions[2 * i + 0], c->positions[2 * i + 1], &sx, &sy);

            if (sx < minx) { minx = sx; }
            if (sx > maxx) { maxx = sx; }
            if (sy < miny) { miny = sy; }
            if (sy > maxy) { maxy = sy; }
        }
    }

    if (maxx < minx)
    {
        return 0;
    }

    if (x0 != nullptr) { *x0 = minx; }
    if (y0 != nullptr) { *y0 = miny; }
    if (x1 != nullptr) { *x1 = maxx; }
    if (y1 != nullptr) { *y1 = maxy; }

    return 1;
}

/*----------------------------------------------------------------- 绘制 */

static void alloc_draw_buffers(int divisor)
{
    int rw = SPINE_SCR_W / divisor;
    int rh = SPINE_SCR_H / divisor;

    for (int i = 0; i < 3; i++)
    {
        if (g_d.lows[i] != nullptr)
        {
            spine_heap_free(g_d.lows[i]);
            g_d.lows[i] = nullptr;
        }
    }

    for (int i = 0; i < 3; i++)
    {
        g_d.lows[i] = (uint16_t *)spine_heap_alloc((size_t)rw * rh * 2u);

        if (g_d.lows[i] == nullptr)
        {
            printf("[API] low-res buffer alloc failed\r\n");
            return;
        }
    }

    g_d.divisor = divisor;
    g_d.inv_divisor = 1.0f / (float)divisor;
    g_d.rw = rw;
    g_d.rh = rh;

    g_d.surf.w = rw;
    g_d.surf.h = rh;
    g_d.surf.stride = rw;
    g_d.surf.clip_x0 = 0;
    g_d.surf.clip_y0 = 0;
    g_d.surf.clip_x1 = rw - 1;
    g_d.surf.clip_y1 = rh - 1;

    /* 全清三块前台缓冲与三块低分辨率缓冲 */
    for (int i = 0; i < 3; i++)
    {
        raster_surface_t fs;

        fs.px = g_d.bufs[i];
        fs.w = SPINE_SCR_W;
        fs.h = SPINE_SCR_H;
        fs.stride = SPINE_SCR_W;
        fs.clip_x0 = 0;
        fs.clip_y0 = 0;
        fs.clip_x1 = SPINE_SCR_W - 1;
        fs.clip_y1 = SPINE_SCR_H - 1;
        raster_clear(&fs, SPINE_BG);
        raster_flush(g_d.bufs[i], SPINE_SCR_W * SPINE_SCR_H * 2);

        g_d.surf.px = g_d.lows[i];
        raster_clear(&g_d.surf, SPINE_BG);

        g_d.pbx[i] = 0;
        g_d.pby[i] = 0;
        g_d.pbX[i] = -1;
        g_d.pbY[i] = -1;
    }

    g_d.draw_idx = 1;
    g_d.inited = 1;

    api_set_framebuffer(g_d.bufs[0]);
}

void spine_draw_begin(int divisor)
{
    if (divisor < 1)
    {
        divisor = 1;
    }

    for (int i = 0; i < 3; i++)
    {
        g_d.bufs[i] = (uint16_t *)plat_fb_addr(i);
    }

    if ((g_d.verts == nullptr) || (g_d.divisor != divisor) || (!g_d.inited))
    {
        if (g_d.verts == nullptr)
        {
            g_d.verts = (raster_vertex_t *)spine_heap_alloc(sizeof(raster_vertex_t) * SPINE_MAX_VERTS);

            if (g_d.verts == nullptr)
            {
                printf("[API] vertex buffer alloc failed\r\n");
                return;
            }
        }

        alloc_draw_buffers(divisor);
    }

    g_d.surf.px = (divisor == 1) ? g_d.bufs[g_d.draw_idx] : g_d.lows[g_d.draw_idx];

    g_d.qcount = 0;
    g_d.have_bbox = 0;
    g_d.fbx0 = 0;
    g_d.fby0 = 0;
    g_d.fbx1 = -1;
    g_d.fby1 = -1;
}

void spine_instance_draw(spine_instance_t *in)
{
    if ((in == nullptr) || (!g_d.inited))
    {
        return;
    }

    if (in->cmds == nullptr)
    {
        in->cmds = in->renderer->render(*in->skel);
    }

    if (g_d.qcount < SPINE_MAX_INST)
    {
        g_d.queue[g_d.qcount++] = in;
    }

    /* 累加本帧包围盒 */
    for (spine::RenderCommand *c = in->cmds; c != nullptr; c = c->next)
    {
        for (int i = 0; i < c->numVertices; i++)
        {
            float sx, sy;

            api_xform(in, c->positions[2 * i + 0], c->positions[2 * i + 1], &sx, &sy);

            int ix0 = (int)(sx * g_d.inv_divisor);
            int iy0 = (int)(sy * g_d.inv_divisor);

            if (!g_d.have_bbox)
            {
                g_d.fbx0 = g_d.fbx1 = ix0;
                g_d.fby0 = g_d.fby1 = iy0;
                g_d.have_bbox = 1;
            }
            else
            {
                if (ix0 < g_d.fbx0) { g_d.fbx0 = ix0; }
                if (ix0 > g_d.fbx1) { g_d.fbx1 = ix0; }
                if (iy0 < g_d.fby0) { g_d.fby0 = iy0; }
                if (iy0 > g_d.fby1) { g_d.fby1 = iy0; }
            }
        }
    }
}

int spine_draw_queue_count(void)
{
    return g_d.qcount;
}

static void draw_one(spine_instance_t *in, raster_surface_t *surf)
{
    raster_vertex_t *verts = g_d.verts;

    if (verts == nullptr)
    {
        return;
    }

    for (spine::RenderCommand *cmd = in->cmds; cmd != nullptr; cmd = cmd->next)
    {
        const RawTexture *tex = (const RawTexture *)cmd->texture;

        if ((tex == nullptr) || (cmd->numVertices <= 0) || (cmd->numVertices > SPINE_MAX_VERTS))
        {
            continue;
        }

        int n = cmd->numVertices;

        for (int i = 0; i < n; i++)
        {
            float sx, sy;

            api_xform(in, cmd->positions[2 * i + 0], cmd->positions[2 * i + 1], &sx, &sy);

            /* 实例的 position/scale 是屏幕像素；绘制目标是 divisor 倍小（半分辨率），
             * 所以渲染坐标要除以 divisor，放大后才会回到正确位置。 */
            verts[i].x = sx * g_d.inv_divisor;
            verts[i].y = sy * g_d.inv_divisor;
            verts[i].u = cmd->uvs[2 * i + 0] * (float)tex->w;
            verts[i].v = cmd->uvs[2 * i + 1] * (float)tex->h;
            verts[i].color = (in->tint == 0xFFFFFFFFu) ? cmd->colors[i]
                                                       : mul_color(cmd->colors[i], in->tint);
        }

        raster_texture_t rt;

        rt.px = tex->px;
        rt.w = tex->w;
        rt.h = tex->h;
        rt.stride = tex->w;
        rt.fmt = (tex->fmt == 2u) ? RASTER_FMT_ARGB4444 : RASTER_FMT_ARGB1555;
        rt.key = 0;

        raster_mesh(surf, &rt, verts, n, cmd->indices, cmd->numIndices,
                    (raster_blend_t)spine_blend_of(cmd->blendMode), in->alpha);
    }
}

void spine_draw_end(void)
{
    if (!g_d.inited)
    {
        return;
    }

    int idx = g_d.draw_idx;

    /* 脏矩形 = 本帧包围盒 ∪ 该缓冲上一帧包围盒 */
    int dbx0 = g_d.fbx0;
    int dby0 = g_d.fby0;
    int dbx1 = g_d.fbx1;
    int dby1 = g_d.fby1;

    if (g_d.have_bbox && (g_d.pbX[idx] >= 0))
    {
        if (g_d.pbx[idx] < dbx0) { dbx0 = g_d.pbx[idx]; }
        if (g_d.pby[idx] < dby0) { dby0 = g_d.pby[idx]; }
        if (g_d.pbX[idx] > dbx1) { dbx1 = g_d.pbX[idx]; }
        if (g_d.pbY[idx] > dby1) { dby1 = g_d.pbY[idx]; }
    }

    /* 留一点余量防止边缘漏清 */
    dbx0 -= 2; dby0 -= 2; dbx1 += 2; dby1 += 2;

    if (!g_d.have_bbox)
    {
        dbx0 = 0; dby0 = 0; dbx1 = -1; dby1 = -1;
    }

    if (dbx0 < 0) { dbx0 = 0; }
    if (dby0 < 0) { dby0 = 0; }
    if (dbx1 > g_d.rw - 1) { dbx1 = g_d.rw - 1; }
    if (dby1 > g_d.rh - 1) { dby1 = g_d.rh - 1; }

    if (dbx1 >= dbx0)
    {
        fill_rect(&g_d.surf, dbx0, dby0, dbx1, dby1, SPINE_BG);
    }

    for (int i = 0; i < g_d.qcount; i++)
    {
        draw_one(g_d.queue[i], &g_d.surf);
    }

    uint16_t *dst = g_d.bufs[idx];

    if (g_d.divisor == 1)
    {
        if (plat_fb_need_cache_clean())
        {
            raster_flush(dst, SPINE_SCR_W * SPINE_SCR_H * 2u);
        }
    }
    else
    {
        if (dbx1 >= dbx0)
        {
            raster_upscale2x(g_d.lows[idx], g_d.rw, dst, SPINE_SCR_W, dbx0, dby0, dbx1, dby1);

            if (plat_fb_need_cache_clean())
            {
                raster_flush(dst + (size_t)(2 * dby0) * SPINE_SCR_W,
                             (dbx1 - dbx0 + 1) * 4 * (dby1 - dby0 + 1) * 2);
            }
        }
    }

    /* 记录本帧包围盒，供该缓冲三帧后再用 */
    g_d.pbx[idx] = g_d.fbx0;
    g_d.pby[idx] = g_d.fby0;
    g_d.pbX[idx] = g_d.fbx1;
    g_d.pbY[idx] = g_d.fby1;

    api_set_framebuffer(dst);

    g_d.draw_idx = (idx + 1) % 3;
}

/*----------------------------------------------------------------- 世界重力 */

void spine_world_set_gravity(float gx, float gy)
{
    g_gx = gx;
    g_gy = gy;

    for (int i = 0; i < g_reg_count; i++)
    {
        if (g_reg[i] != nullptr)
        {
            g_reg[i]->skel->setGravityX(gx);
            g_reg[i]->skel->setGravityY(gy);
        }
    }
}

float spine_world_get_gravity_x(void) { return g_gx; }
float spine_world_get_gravity_y(void) { return g_gy; }

int spine_world_instance_count(void)
{
    return g_reg_count;
}
