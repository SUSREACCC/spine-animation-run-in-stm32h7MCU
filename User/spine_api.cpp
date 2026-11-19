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
#include <spine/IkConstraint.h>
#include <spine/Bone.h>
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
#define SPINE_IK_MAX        4

typedef struct
{
    spine::IkConstraint *ik;
    float wx, wy;              /* 覆盖目标（世界坐标） */
    float base_lx, base_ly;    /* 首次覆盖前目标骨骼的局部姿态 */
    int   captured;
} spine_ik_slot_t;
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
    spine::TrackEntry         *retire[4];  /* 上一代条目：混合完成后再回收 */

    float    x, y;                          /* 世界原点在屏幕上的位置 */
    float    scale;
    float    flip_x, flip_y;
    uint32_t tint;

    /* IK 目标覆盖（运行时驱动用） */
    spine_ik_slot_t ik[SPINE_IK_MAX];                          /* RGBA8888 */

    /* IK 混入覆盖：必须在 AnimationState::apply() 之后写入才不会被动画覆盖 */
    struct { spine::IkConstraint *ik; float mix; } mix[SPINE_IK_MAX];
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
    int      force_full;
    int      fbx0, fby0, fbx1, fby1;
} g_d;

/*----------------------------------------------------------------- 覆盖层 */

#define SPINE_OV_MAX      32
#define SPINE_OV_TEXT_MAX 48

typedef struct
{
    uint8_t  type;                 /* 0=矩形 1=边框 2=文本 */
    int16_t  x0, y0, x1, y1;
    int16_t  thick;
    uint16_t color;
    char     text[SPINE_OV_TEXT_MAX];
} spine_ov_op_t;

static spine_ov_op_t g_ov[SPINE_OV_MAX];
static int           g_ov_count = 0;
static int           g_ov_have_bbox = 0;
static int           g_ov_bx0, g_ov_by0, g_ov_bx1, g_ov_by1;

int spine_overlay_count(void)
{
    return g_ov_count;
}

/* 把一块 divisor×divisor 的像素写进 surface（半分辨率时一个屏幕像素 = 一块） */
static void ov_block(raster_surface_t *s, int sx, int sy, int n, uint16_t color)
{
    int x1 = sx + n - 1;
    int y1 = sy + n - 1;

    if (sx < s->clip_x0) { sx = s->clip_x0; }
    if (sy < s->clip_y0) { sy = s->clip_y0; }
    if (x1 > s->clip_x1) { x1 = s->clip_x1; }
    if (y1 > s->clip_y1) { y1 = s->clip_y1; }
    if ((sx > x1) || (sy > y1)) { return; }

    for (int y = sy; y <= y1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        for (int x = sx; x <= x1; x++)
        {
            row[x] = color;
        }
    }
}

/* 屏幕像素矩形 -> surface 上的填充（inv=1 全分辨率；inv=0.5 半分辨率） */
static void ov_rect_scaled(raster_surface_t *s, float inv,
                           int x0, int y0, int x1, int y1, uint16_t color)
{
    int sx0 = (int)((float)x0 * inv);
    int sy0 = (int)((float)y0 * inv);
    int sx1 = (int)((float)(x1 + 1) * inv) - 1;
    int sy1 = (int)((float)(y1 + 1) * inv) - 1;

    if (sx0 < s->clip_x0) { sx0 = s->clip_x0; }
    if (sy0 < s->clip_y0) { sy0 = s->clip_y0; }
    if (sx1 > s->clip_x1) { sx1 = s->clip_x1; }
    if (sy1 > s->clip_y1) { sy1 = s->clip_y1; }
    if ((sx1 < sx0) || (sy1 < sy0)) { return; }

    uint32_t v = ((uint32_t)color << 16) | (uint32_t)color;

    for (int y = sy0; y <= sy1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        /* 偶数对齐时用 32 位写，快一倍 */
        if (((sx0 & 1) == 0) && (sx1 > sx0))
        {
            int n = ((sx1 - sx0 + 1) >> 1);
            uint32_t *w = (uint32_t *)(row + sx0);

            for (int i = 0; i < n; i++)
            {
                w[i] = v;
            }

            if ((sx1 - sx0 + 1) & 1)
            {
                row[sx1] = color;
            }
        }
        else
        {
            for (int x = sx0; x <= sx1; x++)
            {
                row[x] = color;
            }
        }
    }
}

/* 16 px ASCII 字库（板级定义在 lcdfont.h / lcd.c，这里只声明，不重复定义） */
/* 自带 5x7 字库（由 gen_font.py 生成），不依赖板级字模 */
#include "spine_font.h"

/**
 * 渲染一段 ASCII 文本。
 * @param scale 放大倍数（1 => 5x7，2 => 10x14），字符步进 (5+1)*scale
 */
static void ov_text_at(raster_surface_t *s, int x, int y,
                       const char *str, uint16_t color, int scale)
{
    if (scale < 1)
    {
        scale = 1;
    }

    const int step = (SPINE_FONT_W + 1) * scale;

    for (const char *p = str; (*p != 0); p++)
    {
        unsigned char c = (unsigned char)(*p);

        /* 字库只有大写：小写统一折成大写，避免整段变空白 */
        if ((c >= 'a') && (c <= 'z'))
        {
            c = (unsigned char)(c - 'a' + 'A');
        }

        int idx = (int)c - SPINE_FONT_FIRST;

        if (idx < 0 || idx > (SPINE_FONT_LAST - SPINE_FONT_FIRST))
        {
            idx = 0;
        }

        const uint8_t *g = g_spine_font[idx];

        for (int col = 0; col < SPINE_FONT_W; col++)
        {
            uint8_t bits = g[col];

            for (int row = 0; row < SPINE_FONT_H; row++)
            {
                if (((bits >> row) & 1u) == 0u)
                {
                    continue;
                }

                int bx = x + col * scale;
                int by = y + row * scale;

                for (int dy = 0; dy < scale; dy++)
                {
                    for (int dx = 0; dx < scale; dx++)
                    {
                        ov_block(s, bx + dx, by + dy, 1, color);
                    }
                }
            }
        }

        x += step;
    }
}

/* 覆盖层自己的包围盒（与帧脏矩形分开；内容没变就不并进去） */
static void ov_extend_bbox(int x0, int y0, int x1, int y1)
{
    if (!g_ov_have_bbox)
    {
        g_ov_bx0 = x0;
        g_ov_by0 = y0;
        g_ov_bx1 = x1;
        g_ov_by1 = y1;
        g_ov_have_bbox = 1;
        return;
    }

    if (x0 < g_ov_bx0) { g_ov_bx0 = x0; }
    if (y0 < g_ov_by0) { g_ov_by0 = y0; }
    if (x1 > g_ov_bx1) { g_ov_bx1 = x1; }
    if (y1 > g_ov_by1) { g_ov_by1 = y1; }
}

void spine_overlay_rect(int x0, int y0, int x1, int y1, uint16_t color565)
{
    if ((g_ov_count >= SPINE_OV_MAX) || (!g_d.inited))
    {
        return;
    }

    if (x0 > x1) { int t = x0; x0 = x1; x1 = t; }
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }

    spine_ov_op_t *op = &g_ov[g_ov_count++];

    op->type = 0;
    op->x0 = (int16_t)x0;
    op->y0 = (int16_t)y0;
    op->x1 = (int16_t)x1;
    op->y1 = (int16_t)y1;
    op->thick = 0;
    op->color = color565;

    ov_extend_bbox(x0, y0, x1, y1);
}

void spine_overlay_frame(int x0, int y0, int x1, int y1, int thick, uint16_t color565)
{
    if ((g_ov_count >= SPINE_OV_MAX) || (!g_d.inited))
    {
        return;
    }

    if (x0 > x1) { int t = x0; x0 = x1; x1 = t; }
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }
    if (thick < 1) { thick = 1; }

    spine_ov_op_t *op = &g_ov[g_ov_count++];

    op->type = 1;
    op->x0 = (int16_t)x0;
    op->y0 = (int16_t)y0;
    op->x1 = (int16_t)x1;
    op->y1 = (int16_t)y1;
    op->thick = (int16_t)thick;
    op->color = color565;

    ov_extend_bbox(x0, y0, x1, y1);
}

void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565)
{
    if ((ascii == nullptr) || (g_ov_count >= SPINE_OV_MAX) || (!g_d.inited))
    {
        return;
    }

    spine_ov_op_t *op = &g_ov[g_ov_count++];
    int i = 0;

    op->type = 2;
    op->x0 = (int16_t)x;
    op->y0 = (int16_t)y;
    op->thick = 2;                  /* 默认 scale = 2（10x14 像素） */
    op->color = color565;

    for (; (ascii[i] != 0) && (i < (SPINE_OV_TEXT_MAX - 1)); i++)
    {
        op->text[i] = ascii[i];
    }
    op->text[i] = 0;

    op->x1 = (int16_t)(x + i * 12 + 2);
    op->y1 = (int16_t)(y + 14);

    ov_extend_bbox(x, y, op->x1, op->y1);
}

/* 由 spine_draw_end() 在实例绘制之后调用 */
static void spine_overlay_flush(raster_surface_t *s, float inv)
{
    for (int i = 0; i < g_ov_count; i++)
    {
        spine_ov_op_t *op = &g_ov[i];

        switch (op->type)
        {
            case 0:
                ov_rect_scaled(s, inv, op->x0, op->y0, op->x1, op->y1, op->color);
                break;

            case 1:
            {
                int t = op->thick;

                ov_rect_scaled(s, inv, op->x0, op->y0, op->x1, op->y0 + t - 1, op->color);
                ov_rect_scaled(s, inv, op->x0, op->y1 - t + 1, op->x1, op->y1, op->color);
                ov_rect_scaled(s, inv, op->x0, op->y0, op->x0 + t - 1, op->y1, op->color);
                ov_rect_scaled(s, inv, op->x1 - t + 1, op->y0, op->x1, op->y1, op->color);
                break;
            }

            case 2:
                ov_text_at(s, op->x0, op->y0, op->text, op->color, (op->thick > 0) ? op->thick : 2);
                break;

            default:
                break;
        }
    }
}

/*----------------------------------------------------------------- IK 约束 */

int spine_instance_ik_count(spine_instance_t *in)
{
    if ((in == nullptr) || (in->skel == nullptr))
    {
        return 0;
    }

    spine::Array<spine::Constraint *> &cs = in->skel->getConstraints();
    int n = 0;

    for (size_t i = 0; i < cs.size(); i++)
    {
        if (cs[i]->getRTTI().instanceOf(spine::IkConstraint::rtti))
        {
            n++;
        }
    }

    return n;
}

static spine::IkConstraint *ik_at(spine_instance_t *in, int index)
{
    if ((in == nullptr) || (in->skel == nullptr) || (index < 0))
    {
        return nullptr;
    }

    spine::Array<spine::Constraint *> &cs = in->skel->getConstraints();
    int n = 0;

    for (size_t i = 0; i < cs.size(); i++)
    {
        if (cs[i]->getRTTI().instanceOf(spine::IkConstraint::rtti))
        {
            if (n == index)
            {
                return (spine::IkConstraint *)cs[i];
            }
            n++;
        }
    }

    return nullptr;
}

const char *spine_instance_ik_name(spine_instance_t *in, int index)
{
    spine::IkConstraint *ik = ik_at(in, index);

    return (ik == nullptr) ? nullptr : ik->getData().getName().buffer();
}

static spine::IkConstraint *ik_by_name(spine_instance_t *in, const char *name)
{
    if ((in == nullptr) || (in->skel == nullptr) || (name == nullptr) || (name[0] == 0))
    {
        return nullptr;
    }

    return in->skel->findConstraint<spine::IkConstraint>(spine::String(name));
}

int spine_instance_ik_bone_count(spine_instance_t *in, const char *ik_name)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    return (ik == nullptr) ? 0 : (int)ik->getBones().size();
}

int spine_instance_set_ik_target(spine_instance_t *in, const char *ik_name,
                                 float world_x, float world_y)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if ((ik == nullptr) || (world_x != world_x) || (world_y != world_y))
    {
        return 0;                   /* 找不到，或传了 NaN */
    }

    spine_ik_slot_t *slot = nullptr;

    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->ik[i].ik == ik)
        {
            slot = &in->ik[i];
            break;
        }

        if ((slot == nullptr) && (in->ik[i].ik == nullptr))
        {
            slot = &in->ik[i];
        }
    }

    if (slot == nullptr)
    {
        return 0;                   /* 覆盖槽满了 */
    }

    if ((slot->captured == 0) || (slot->ik != ik))
    {
        /* 记住覆盖前的目标骨骼姿态，clear 时原样还回去 */
        spine::BonePose &base = ik->getTarget().getAppliedPose();

        slot->base_lx = base.getX();
        slot->base_ly = base.getY();
        slot->captured = 1;
    }

    slot->ik = ik;
    slot->wx = world_x;
    slot->wy = world_y;

    return 1;
}

int spine_instance_get_ik_target(spine_instance_t *in, const char *ik_name,
                                 float *world_x, float *world_y)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if (ik == nullptr)
    {
        return 0;
    }

    spine::BonePose *p = &ik->getTarget().getAppliedPose();

    if (world_x != nullptr) { *world_x = p->getWorldX(); }
    if (world_y != nullptr) { *world_y = p->getWorldY(); }

    return 1;
}

int spine_instance_get_ik_tip(spine_instance_t *in, const char *ik_name,
                              float *world_x, float *world_y)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if ((ik == nullptr) || (ik->getBones().size() == 0))
    {
        return 0;
    }

    /* getBones() 返回的是 _constrainedPose 子对象，必须经 BoneData 索引换回 Bone */
    spine::IkConstraintData &d = (spine::IkConstraintData &)ik->getData();
    spine::Array<spine::BoneData *> &bds = d.getBones();

    if (bds.size() == 0)
    {
        return 0;
    }

    spine::BoneData *last = bds[bds.size() - 1];
    spine::Bone &bone = *in->skel->getBones()[last->getIndex()];

    float tx = 0.0f, ty = 0.0f;

    bone.getAppliedPose().localToWorld(bone.getData().getLength(), 0.0f, tx, ty);

    if (world_x != nullptr) { *world_x = tx; }
    if (world_y != nullptr) { *world_y = ty; }

    return 1;
}

float spine_instance_ik_mix(spine_instance_t *in, const char *ik_name)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if (ik == nullptr)
    {
        return 0.0f;
    }

    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->mix[i].ik == ik)
        {
            return in->mix[i].mix;
        }
    }

    return ik->getPose().getMix();
}

int spine_instance_set_ik_mix(spine_instance_t *in, const char *ik_name, float mix)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if (ik == nullptr)
    {
        return 0;
    }

    if (mix < 0.0f) { mix = 0.0f; }
    if (mix > 1.0f) { mix = 1.0f; }

    /* 不能直接写：动画的 IK mix 时间轴会在每帧 apply() 时覆盖它。
     * 存起来，交给 apply_ik_overrides() 在 apply() 之后写。 */
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if ((in->mix[i].ik == ik) || (in->mix[i].ik == nullptr))
        {
            in->mix[i].ik = ik;
            in->mix[i].mix = mix;

            /* 立刻也写一遍，保证不含 update 的路径（如 get 读回）一致 */
            ik->getPose().setMix(mix);

            return 1;
        }
    }

    return 0;                       /* 槽满了 */
}

float spine_instance_ik_mix_applied(spine_instance_t *in, const char *ik_name)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    return (ik == nullptr) ? 0.0f : ik->getAppliedPose().getMix();
}

void spine_instance_release_ik_keep_pose(spine_instance_t *in)
{
    if (in == nullptr)
    {
        return;
    }

    /* 只清覆盖表，不动骨骼姿态 */
    memset(in->ik, 0, sizeof(in->ik));
}

void spine_instance_clear_ik(spine_instance_t *in)
{
    if (in == nullptr)
    {
        return;
    }

    /* 关键：把目标骨骼的姿态还原，否则动画不驱动这根骨骼时，
     * 偏移量会永久留在骨架上（表现为运动范围整体平移）。 */
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if ((in->ik[i].ik != nullptr) && (in->ik[i].captured != 0))
        {
            spine::BonePose &p = in->ik[i].ik->getTarget().getAppliedPose();

            p.setX(in->ik[i].base_lx);
            p.setY(in->ik[i].base_ly);
        }
    }

    memset(in->ik, 0, sizeof(in->ik));
}

/* 在动画 apply 之后、updateWorldTransform 之前把 IK 目标写进目标骨骼 */
static void apply_ik_overrides(spine_instance_t *in)
{
    /* 先写 IK 混入（动画的 mix 时间轴刚在 apply() 里写过，这里夺回控制权） */
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->mix[i].ik != nullptr)
        {
            in->mix[i].ik->getPose().setMix(in->mix[i].mix);
            in->mix[i].ik->getAppliedPose().setMix(in->mix[i].mix);
        }
    }

    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->ik[i].ik == nullptr)
        {
            continue;
        }

        spine::Bone &target = in->ik[i].ik->getTarget();

        float lx = 0.0f, ly = 0.0f;

        target.getAppliedPose().worldToParent(in->ik[i].wx, in->ik[i].wy, lx, ly);

        spine::BonePose &p = target.getAppliedPose();

        p.setX(lx);
        p.setY(ly);
    }
}

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

    /* TrackEntry 由我们手动回收：默认模式会在动画播完时自动 dispose，
     * 而我们缓存了指针（get_time/seek 需要），悬空会直接 HardFault。 */
    in->state->setManualTrackEntryDisposal(true);
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

    for (int i = 0; i < 4; i++)
    {
        if (in->tracks[i] != nullptr)
        {
            in->state->disposeTrackEntry(in->tracks[i]);
            in->tracks[i] = nullptr;
        }

        if (in->retire[i] != nullptr)
        {
            in->state->disposeTrackEntry(in->retire[i]);
            in->retire[i] = nullptr;
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

    {
        spine::TrackEntry *old = in->tracks[track];
        spine::TrackEntry *ne = &in->state->setAnimation((size_t)track, spine::String(anim), (loop != 0));

        /* 只有确认它已经不在任何混合链里，才能回收 */
        if ((in->retire[track] != nullptr) &&
            (in->retire[track] != old) &&
            (in->retire[track] != ne))
        {
            int in_chain = 0;
            spine::TrackEntry *m = ne->getMixingFrom();

            while (m != nullptr)
            {
                if (m == in->retire[track])
                {
                    in_chain = 1;
                    break;
                }

                m = m->getMixingFrom();
            }

            if (in_chain == 0)
            {
                in->state->disposeTrackEntry(in->retire[track]);
            }
        }

        in->retire[track] = old;
        in->tracks[track] = ne;
    }
}

void spine_instance_stop(spine_instance_t *in, int track)
{
    if ((in != nullptr) && (track >= 0) && (track < 4))
    {
        in->state->clearTrack((size_t)track);

        if (in->tracks[track] != nullptr)
        {
            in->state->disposeTrackEntry(in->tracks[track]);
        }

        if (in->retire[track] != nullptr)
        {
            in->state->disposeTrackEntry(in->retire[track]);
        }

        in->tracks[track] = nullptr;
        in->retire[track] = nullptr;
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

/*----------------------------------------------------------------- 动画衔接 */

void spine_instance_set_default_mix(spine_instance_t *in, float seconds)
{
    if ((in == nullptr) || (in->asd == nullptr))
    {
        return;
    }

    if (seconds < 0.0f)
    {
        seconds = 0.0f;
    }

    in->asd->setDefaultMix(seconds);
}

int spine_instance_set_mix(spine_instance_t *in, const char *from, const char *to, float seconds)
{
    if ((in == nullptr) || (in->asd == nullptr) || (in->asset == nullptr) ||
        (from == nullptr) || (to == nullptr))
    {
        return 0;
    }

    /* 先查存在性：setMix(String,String,..) 内部是 assert，名字写错会直接断言 */
    spine::Animation *fa = in->asset->data->findAnimation(spine::String(from));
    spine::Animation *ta = in->asset->data->findAnimation(spine::String(to));

    if ((fa == nullptr) || (ta == nullptr))
    {
        return 0;
    }

    if (seconds < 0.0f)
    {
        seconds = 0.0f;
    }

    in->asd->setMix(*fa, *ta, seconds);

    return 1;
}


/* 返回该轨道上真正在播的条目：排队的动画接管后，沿 next 链跳过旧的 */
static spine::TrackEntry *cur_entry(spine_instance_t *in, int track)
{
    if ((in == nullptr) || (track < 0) || (track >= 4))
    {
        return nullptr;
    }

    spine::TrackEntry *te = in->tracks[track];

    while ((te != nullptr) && (te->getNext() != nullptr))
    {
        if (te->getNext()->getTrackTime() > 0.0f)
        {
            te = te->getNext();     /* 下一段已开始 */
        }
        else
        {
            break;                  /* 还在排队的下一段 */
        }
    }

    return te;
}

float spine_instance_anim_duration(spine_instance_t *in, int track)
{
    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return 0.0f;
    }

    return te->getAnimation().getDuration();
}

float spine_instance_anim_time(spine_instance_t *in, int track)
{
    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return 0.0f;
    }

    return te->getAnimationTime();
}

float spine_instance_get_time(spine_instance_t *in, int track)
{
    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return 0.0f;
    }

    return te->getTrackTime();
}

const char *spine_instance_current_anim(spine_instance_t *in, int track)
{
    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return nullptr;
    }

    return te->getAnimation().getName().buffer();
}

int spine_instance_seek(spine_instance_t *in, float seconds, int track)
{
    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return 0;
    }

    if (seconds < 0.0f)
    {
        seconds = 0.0f;
    }

    /* 保留 timeScale：set_time() 会清零做成"定格"，接回进度时不能这样 */
    float ts = te->getTimeScale();

    te->setTrackTime(seconds);
    te->setTimeScale(ts);

    return 1;
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

    /* IK 目标覆盖：必须在 apply 之后写入，否则会被动画轨道覆盖 */
    apply_ik_overrides(in);

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
    g_ov_count = 0;
    g_ov_have_bbox = 0;
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

void spine_draw_force_full(void)
{
    g_d.force_full = 1;
}

void spine_draw_end(void)
{
    if (!g_d.inited)
    {
        return;
    }

    int idx = g_d.draw_idx;

    if (g_d.force_full != 0)
    {
        /* 整屏脏矩形：正常路径会填充 + 放大整屏，不会留下上一帧的残留像素 */
        g_d.fbx0 = 0;
        g_d.fby0 = 0;
        g_d.fbx1 = g_d.rw - 1;
        g_d.fby1 = g_d.rh - 1;
        g_d.have_bbox = 1;
        g_d.force_full = 0;
    }

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

    /* ---- 覆盖层：直接画到全分辨率目标（放大之后），文字清晰且每帧一致 ---- */
    if (g_ov_count > 0)
    {
        /* 覆盖层必须画进**所有**缓冲：
         * 三缓冲下每块缓冲要 3 帧才轮到一次，只画 dst 会让三块显示不同的
         * HUD 内容（文字变化时闪烁），并与上一帧残留叠加（混叠）。 */
        int nfb = plat_fb_count();

        if (nfb > 3)
        {
            nfb = 3;
        }

        for (int b = 0; b < nfb; b++)
        {
            raster_surface_t full;
            uint16_t *target = g_d.bufs[b];

            if (target == nullptr)
            {
                continue;
            }

            full.px = target;
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

                    plat_cache_clean(target + (size_t)oy * SPINE_SCR_W + x0,
                                     (size_t)(x1 - x0 + 1) * 2u);
                }
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
