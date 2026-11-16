/**
 ****************************************************************************************************
 * @file        raster2d.cpp
 * @brief       面向 Spine 的 2D 纹理三角形光栅器实现
 * @note        三个关键设计：
 *
 *   1) 内层循环用「扫描线区间」：每行先解出 x_left/x_right，像素循环内没有任何边界判定；
 *      区间端点再用定点边函数校验，因此 top-left 语义与逐像素判定完全等价。
 *
 *   2) 混合在 **RGB565 原生空间** 完成（blend565）：NORMAL 不做 8bit 展开/回包，
 *      省掉每像素约 18 条指令。
 *
 *   3) 色调分三档（COLMODE），覆盖 Spine 的实际分布：
 *        0 = 常量色（整三角形同色）→ 最省
 *        1 = RGB 恒定、仅 alpha 逐顶点变化（slot alpha，最常见）→ 只插值 1 个通道
 *        2 = 完整逐顶点 ARGB
 *
 *   其余：顶点定点化前 clamp 到 ±2048 px（int32 边函数不溢出）；POT 纹理掩码取模。
 ****************************************************************************************************
 */

#include <math.h>
#include <string.h>
#include "raster2d.h"
#include "plat/plat.h"
#include "./SYSTEM/sys/sys.h"

#define COORD_CLAMP     2048.0f
#define SUBPIXEL_BITS   4
#define SUBPIXEL_ONE    (1 << SUBPIXEL_BITS)
#define EDGE_ADJUST_MAX 6

/* 诊断：光栅器实际写出的像素数 */
uint32_t g_raster_px = 0;
extern "C" void raster_pixel_reset(void) { g_raster_px = 0; }
extern "C" uint32_t raster_pixel_count(void) { return g_raster_px; }

#if defined(__ARMCC_VERSION) || defined(__GNUC__) || defined(__clang__)
  #define R2D_AI __attribute__((always_inline)) static inline
#else
  #define R2D_AI static inline
#endif

/*----------------------------------------------------------------- 颜色工具 */

R2D_AI void unpack565(uint16_t c, int &r, int &g, int &b)
{
    int t;

    t = (c >> 11) & 0x1F;  r = (t << 3) | (t >> 2);
    t = (c >> 5) & 0x3F;   g = (t << 2) | (t >> 4);
    t = c & 0x1F;          b = (t << 3) | (t >> 2);
}

R2D_AI uint16_t pack565(int r, int g, int b)
{
    return (uint16_t)(((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3));
}

R2D_AI int mul255(int x, int a)
{
    int t = x * a + 128;
    return (t + (t >> 8)) >> 8;
}

/*----------------------------------------------------------------- 565 原生混合 */

/**
 * RGB565 原生 lerp：dst + (src - dst) * a / 255，逐通道 5/6/5 定点完成。
 * 完全不展开到 8bit，省掉 unpack + pack 共约 18 条指令。
 */
R2D_AI uint16_t lerp565(uint16_t d, uint16_t s, int a)
{
    if (a >= 255)
    {
        return s;
    }
    if (a <= 0)
    {
        return d;
    }

    /* +1 使 a=0 时结果精确等于 dst，避免 5bit 下取整误差累积 */
    int aa = a + 1;

    int dr = (d >> 11) & 0x1F, dg = (d >> 5) & 0x3F, db = d & 0x1F;
    int sr = (s >> 11) & 0x1F, sg = (s >> 5) & 0x3F, sb = s & 0x1F;

    int r = dr + (((sr - dr) * aa) >> 8);
    int g = dg + (((sg - dg) * aa) >> 8);
    int b = db + (((sb - db) * aa) >> 8);

    if (r < 0) { r = 0; } else if (r > 31) { r = 31; }
    if (g < 0) { g = 0; } else if (g > 63) { g = 63; }
    if (b < 0) { b = 0; } else if (b > 31) { b = 31; }

    return (uint16_t)((r << 11) | (g << 5) | b);
}

/** 加法混合（565 原生饱和加） */
R2D_AI uint16_t add565(uint16_t d, uint16_t s, int a)
{
    int sr = (s >> 11) & 0x1F, sg = (s >> 5) & 0x3F, sb = s & 0x1F;

    if (a < 255)
    {
        sr = mul255(sr << 3, a) >> 3;
        sg = mul255(sg << 2, a) >> 2;
        sb = mul255(sb << 3, a) >> 3;
    }

    int r = ((d >> 11) & 0x1F) + sr;
    int g = ((d >> 5) & 0x3F) + sg;
    int b = (d & 0x1F) + sb;

    if (r > 31) { r = 31; }
    if (g > 63) { g = 63; }
    if (b > 31) { b = 31; }

    return (uint16_t)((r << 11) | (g << 5) | b);
}

/* 乘/滤色在 8bit 空间做（少见，不为它们牺牲常见路径的寄存器） */
template <int BLEND>
R2D_AI uint16_t blend8(uint16_t dst, int sr, int sg, int sb, int a)
{
    int dr, dg, db;
    unpack565(dst, dr, dg, db);

    if (BLEND == 2)                     /* multiply */
    {
        int r = dr + mul255(mul255(dr, sr) - dr, a);
        int g = dg + mul255(mul255(dg, sg) - dg, a);
        int b = db + mul255(mul255(db, sb) - db, a);
        return pack565(r, g, b);
    }

    /* screen */
    int r = dr + mul255((255 - mul255(255 - dr, 255 - sr)) - dr, a);
    int g = dg + mul255((255 - mul255(255 - dg, 255 - sg)) - dg, a);
    int b = db + mul255((255 - mul255(255 - db, 255 - sb)) - db, a);
    return pack565(r, g, b);
}

/*----------------------------------------------------------------- 纹理配置 */

struct TexCfg
{
    const uint16_t *px;
    int             stride;
    int             w, h;
    int             mx, my;
    uint16_t        key;
};

R2D_AI TexCfg make_texcfg(const raster_texture_t *t)
{
    TexCfg c;

    c.px = t->px;
    c.stride = t->stride;
    c.w = t->w;
    c.h = t->h;
    c.mx = t->w - 1;
    c.my = t->h - 1;
    c.key = t->key;
    return c;
}

/*----------------------------------------------------------------- 光栅核心 */

/* COLMODE: 0 = 常量色, 1 = RGB 恒定 + 逐顶点 alpha, 2 = 完整逐顶点 ARGB */
template <int FMT, int BLEND, int COLMODE, bool POT, bool RAW_COPY>
static void raster_tri(const raster_surface_t *s, const raster_texture_t *t,
                       const raster_vertex_t *A, const raster_vertex_t *B0,
                       const raster_vertex_t *C0, uint8_t opacity)
{
    const raster_vertex_t *B = B0, *C = C0;

    /* ---------------- 顶点定点化（clamp 后用定点，不再回浮点） ---------------- */
    int32_t AX0, AY0, AX1, AY1, AX2, AY2;
    {
        const raster_vertex_t *V[3] = { A, B, C };
        int32_t *px[3] = { &AX0, &AX1, &AX2 };
        int32_t *py[3] = { &AY0, &AY1, &AY2 };

        for (int i = 0; i < 3; i++)
        {
            float fx = V[i]->x, fy = V[i]->y;

            if (fx < -COORD_CLAMP) { fx = -COORD_CLAMP; } else if (fx > COORD_CLAMP) { fx = COORD_CLAMP; }
            if (fy < -COORD_CLAMP) { fy = -COORD_CLAMP; } else if (fy > COORD_CLAMP) { fy = COORD_CLAMP; }

            *px[i] = (int32_t)lrintf(fx * SUBPIXEL_ONE);
            *py[i] = (int32_t)lrintf(fy * SUBPIXEL_ONE);
        }
    }

    /* ---------------- 绕序统一（纯定点） ---------------- */
    {
        int32_t area = (AX1 - AX0) * (AY2 - AY0) - (AX2 - AX0) * (AY1 - AY0);

        if (area == 0)
        {
            return;
        }
        if (area < 0)
        {
            int32_t ti = AX1; AX1 = AX2; AX2 = ti;
            ti = AY1; AY1 = AY2; AY2 = ti;
            const raster_vertex_t *tv = B; B = C; C = tv;
        }
    }

    /* ---------------- 包围盒：由定点顶点直接取整（省掉浮点 min/max + 转换） ---------------- */
    int bx0, bx1, by0, by1;
    {
        int32_t minX = AX0, maxX = AX0, minY = AY0, maxY = AY0;

        if (AX1 < minX) { minX = AX1; }
        if (AX1 > maxX) { maxX = AX1; }
        if (AX2 < minX) { minX = AX2; }
        if (AX2 > maxX) { maxX = AX2; }
        if (AY1 < minY) { minY = AY1; }
        if (AY1 > maxY) { maxY = AY1; }
        if (AY2 < minY) { minY = AY2; }
        if (AY2 > maxY) { maxY = AY2; }

        bx0 = minX >> SUBPIXEL_BITS;                            /* floor */
        bx1 = (maxX + (SUBPIXEL_ONE - 1)) >> SUBPIXEL_BITS;     /* ceil  */
        by0 = minY >> SUBPIXEL_BITS;
        by1 = (maxY + (SUBPIXEL_ONE - 1)) >> SUBPIXEL_BITS;
    }

    if (bx0 < s->clip_x0) { bx0 = s->clip_x0; }
    if (by0 < s->clip_y0) { by0 = s->clip_y0; }
    if (bx1 > s->clip_x1) { bx1 = s->clip_x1; }
    if (by1 > s->clip_y1) { by1 = s->clip_y1; }
    if ((bx0 > bx1) || (by0 > by1))
    {
        return;
    }

    /* ---------------- 边增量 ---------------- */
    const int32_t X0 = AX0, Y0 = AY0, X1 = AX1, Y1 = AY1, X2 = AX2, Y2 = AY2;
    const int32_t dw0dx = -(AY1 - AY0) * SUBPIXEL_ONE, dw0dy = (AX1 - AX0) * SUBPIXEL_ONE;
    const int32_t dw1dx = -(AY2 - AY1) * SUBPIXEL_ONE, dw1dy = (AX2 - AX1) * SUBPIXEL_ONE;
    const int32_t dw2dx = -(AY0 - AY2) * SUBPIXEL_ONE, dw2dy = (AX0 - AX2) * SUBPIXEL_ONE;

    int32_t px0 = (bx0 << SUBPIXEL_BITS) + (SUBPIXEL_ONE / 2);
    int32_t py0 = (by0 << SUBPIXEL_BITS) + (SUBPIXEL_ONE / 2);

    int32_t w0_row = (AX1 - AX0) * (py0 - Y0) - (AY1 - AY0) * (px0 - X0);
    int32_t w1_row = (AX2 - AX1) * (py0 - Y1) - (AY2 - AY1) * (px0 - X1);
    int32_t w2_row = (AX0 - AX2) * (py0 - Y2) - (AY0 - AY2) * (px0 - X2);

    w0_row += ((dw0dx > 0) || ((dw0dx == 0) && (dw0dy > 0))) ? 0 : -1;
    w1_row += ((dw1dx > 0) || ((dw1dx == 0) && (dw1dy > 0))) ? 0 : -1;
    w2_row += ((dw2dx > 0) || ((dw2dx == 0) && (dw2dy > 0))) ? 0 : -1;

    /* 浮点求交用的顶点坐标（由已归一绕序的定点顶点导出） */
    const float ax = (float)AX0 * (1.0f / 16.0f), ay = (float)AY0 * (1.0f / 16.0f);
    const float bx = (float)AX1 * (1.0f / 16.0f), by = (float)AY1 * (1.0f / 16.0f);
    const float cx = (float)AX2 * (1.0f / 16.0f), cy = (float)AY2 * (1.0f / 16.0f);

    /* ---------------- 三条边的 x(y) ---------------- */
    float vx[3] = { ax, bx, cx };
    float vy[3] = { ay, by, cy };
    float ex_int[3], ey_lo[3], ey_hi[3], e_slope[3];

    for (int e = 0; e < 3; e++)
    {
        int a = e, b = (e + 1) % 3;
        float ya = vy[a], yb = vy[b];
        float xa = vx[a], xb = vx[b];

        ey_lo[e] = ya < yb ? ya : yb;
        ey_hi[e] = ya < yb ? yb : ya;

        float dy = yb - ya;

        if (fabsf(dy) < 0.0001f)
        {
            e_slope[e] = 0.0f;
            ex_int[e] = xa;
        }
        else
        {
            e_slope[e] = (xb - xa) / dy;
            ex_int[e] = xa - ya * e_slope[e];
        }
    }

    /* ---------------- UV / 颜色梯度 ---------------- */
    float det = (B->x - A->x) * (C->y - A->y) - (C->x - A->x) * (B->y - A->y);

    if (det == 0.0f)
    {
        return;
    }
    float inv = 1.0f / det;

    float du_dx = ((B->u - A->u) * (C->y - A->y) - (C->u - A->u) * (B->y - A->y)) * inv;
    float dv_dx = ((B->v - A->v) * (C->y - A->y) - (C->v - A->v) * (B->y - A->y)) * inv;
    float du_dy = ((C->u - A->u) * (B->x - A->x) - (B->u - A->u) * (C->x - A->x)) * inv;
    float dv_dy = ((C->v - A->v) * (B->x - A->x) - (B->v - A->v) * (C->x - A->x)) * inv;

    /* 常量色（三顶点相同） */
    int cr_c = (A->color >> 16) & 0xFF;
    int cg_c = (A->color >> 8) & 0xFF;
    int cb_c = A->color & 0xFF;

    /* alpha 梯度（COLMODE 1/2 需要） */
    float da_dx = 0.0f, da_dy = 0.0f;
    int   ca0 = 255;

    if (COLMODE != 0)
    {
        ca0 = (A->color >> 24) & 0xFF;
        float ba = (float)((B->color >> 24) & 0xFF) - (float)ca0;
        float xa = (float)((C->color >> 24) & 0xFF) - (float)ca0;

        da_dx = (ba * (C->y - A->y) - xa * (B->y - A->y)) * inv;
        da_dy = (xa * (B->x - A->x) - ba * (C->x - A->x)) * inv;
    }

    /* RGB 梯度（只有 COLMODE 2 需要） */
    float dcrdx = 0.0f, dcgdx = 0.0f, dcbdx = 0.0f, dcrdy = 0.0f, dcgdy = 0.0f, dcbdy = 0.0f;

    if (COLMODE == 2)
    {
        float br = (float)((B->color >> 16) & 0xFF) - (float)cr_c;
        float bg = (float)((B->color >> 8) & 0xFF) - (float)cg_c;
        float bb = (float)(B->color & 0xFF) - (float)cb_c;
        float xr = (float)((C->color >> 16) & 0xFF) - (float)cr_c;
        float xg = (float)((C->color >> 8) & 0xFF) - (float)cg_c;
        float xb = (float)(C->color & 0xFF) - (float)cb_c;

        dcrdx = (br * (C->y - A->y) - xr * (B->y - A->y)) * inv;
        dcgdx = (bg * (C->y - A->y) - xg * (B->y - A->y)) * inv;
        dcbdx = (bb * (C->y - A->y) - xb * (B->y - A->y)) * inv;

        dcrdy = (xr * (B->x - A->x) - br * (C->x - A->x)) * inv;
        dcgdy = (xg * (B->x - A->x) - bg * (C->x - A->x)) * inv;
        dcbdy = (xb * (B->x - A->x) - bb * (C->x - A->x)) * inv;
    }

    TexCfg tex = make_texcfg(t);

    /* ---- 1555 快路径的循环不变前置计算 ---- */
    const bool white_tint = (cr_c == 255) && (cg_c == 255) && (cb_c == 255) &&
                            (((A->color >> 24) & 0xFF) == 255);
    const int  t5r = (cr_c * 32 + 127) / 255;      /* 0..32 */
    const int  t5g = (cg_c * 32 + 127) / 255;
    const int  t5b = (cb_c * 32 + 127) / 255;

    /* ---------------- 逐行扫描 ---------------- */
    uint16_t *row = s->px + (size_t)by0 * s->stride;

    for (int y = by0; y <= by1; y++, row += s->stride)
    {
        float fy = (float)y + 0.5f;
        float xa_f = 1e9f, xb_f = -1e9f;

        for (int e = 0; e < 3; e++)
        {
            if ((fy < ey_lo[e]) || (fy > ey_hi[e]))
            {
                continue;
            }

            float xe = ex_int[e] + fy * e_slope[e];

            if (xe < xa_f) { xa_f = xe; }
            if (xe > xb_f) { xb_f = xe; }
        }

        int xa = (int)ceilf(xa_f - 0.5f);
        int xb = (int)floorf(xb_f - 0.5f);

        if (xa < bx0) { xa = bx0; }
        if (xb > bx1) { xb = bx1; }

        if (xa <= xb)
        {
            for (int k = 0; (k < EDGE_ADJUST_MAX) && (xa <= xb); k++)
            {
                int32_t wx0 = w0_row + (xa - bx0) * dw0dx;
                int32_t wx1 = w1_row + (xa - bx0) * dw1dx;
                int32_t wx2 = w2_row + (xa - bx0) * dw2dx;

                if ((wx0 | wx1 | wx2) >= 0)
                {
                    break;
                }
                xa++;
            }

            for (int k = 0; (k < EDGE_ADJUST_MAX) && (xa <= xb); k++)
            {
                int32_t wx0 = w0_row + (xb - bx0) * dw0dx;
                int32_t wx1 = w1_row + (xb - bx0) * dw1dx;
                int32_t wx2 = w2_row + (xb - bx0) * dw2dx;

                if ((wx0 | wx1 | wx2) >= 0)
                {
                    break;
                }
                xb--;
            }

            /* 浮点区间可能比实际覆盖窄：向外扩展，消除接缝 */
            for (int k = 0; (k < 2) && (xa > bx0); k++)
            {
                int32_t wx0 = w0_row + (xa - 1 - bx0) * dw0dx;
                int32_t wx1 = w1_row + (xa - 1 - bx0) * dw1dx;
                int32_t wx2 = w2_row + (xa - 1 - bx0) * dw2dx;

                if ((wx0 | wx1 | wx2) < 0)
                {
                    break;
                }
                xa--;
            }

            for (int k = 0; (k < 2) && (xb < bx1); k++)
            {
                int32_t wx0 = w0_row + (xb + 1 - bx0) * dw0dx;
                int32_t wx1 = w1_row + (xb + 1 - bx0) * dw1dx;
                int32_t wx2 = w2_row + (xb + 1 - bx0) * dw2dx;

                if ((wx0 | wx1 | wx2) < 0)
                {
                    break;
                }
                xb++;
            }
        }

        if (xa <= xb)
        {
            float fx = (float)xa + 0.5f;
            float fy = (float)y + 0.5f;
            float u = A->u + du_dx * (fx - A->x) + du_dy * (fy - A->y);
            float v = A->v + dv_dx * (fx - A->x) + dv_dy * (fy - A->y);
            float ca = 255.0f, cr = 255.0f, cg = 255.0f, cb = 255.0f;

            if (COLMODE != 0)
            {
                ca = (float)ca0 + da_dx * (fx - A->x) + da_dy * (fy - A->y);
            }
            if (COLMODE == 2)
            {
                cr = (float)cr_c + dcrdx * (fx - A->x) + dcrdy * (fy - A->y);
                cg = (float)cg_c + dcgdx * (fx - A->x) + dcgdy * (fy - A->y);
                cb = (float)cb_c + dcbdx * (fx - A->x) + dcbdy * (fy - A->y);
            }

            /* ---- 内层：无边界判定 ---- */
            for (int x = xa; x <= xb; x++)
            {
                int tu = (int)u;
                int tv = (int)v;

                if (POT)
                {
                    tu &= tex.mx;
                    tv &= tex.my;
                }
                else
                {
                    if (tu < 0) { tu = 0; } else if (tu >= tex.w) { tu = tex.w - 1; }
                    if (tv < 0) { tv = 0; } else if (tv >= tex.h) { tv = tex.h - 1; }
                }


                uint16_t texel = tex.px[tv * tex.stride + tu];

                /* ---- ARGB1555 + 常量色 + Normal：在 565/555 空间直接出结果 ---- */
                if constexpr ((FMT == 1) && (COLMODE == 0) && (BLEND == 0))
                {
                    if (white_tint && (opacity >= 255u))
                    {
                        /* 纯位重组：1555 -> 565（绿通道 5->6 位补一位） */
                        if ((texel & 0x8000u) != 0u)
                        {
                            row[x] = (uint16_t)((((texel >> 10) & 0x1F) << 11) |
                                                ((((texel >> 5) & 0x1F) << 1) << 5) |
                                                (texel & 0x1F));
                        }
                    }
                    else if ((texel & 0x8000u) != 0u)
                    {
                        int r5 = (texel >> 10) & 0x1F;
                        int g5 = (texel >> 5) & 0x1F;
                        int b5 = texel & 0x1F;

                        r5 = (r5 * t5r + 16) >> 5;
                        g5 = (g5 * t5g + 16) >> 5;
                        b5 = (b5 * t5b + 16) >> 5;

                        uint16_t s565 = (uint16_t)((r5 << 11) | (g5 << 6) | b5);

                        int ta = mul255(opacity, (A->color >> 24) & 0xFF);

                        row[x] = (ta >= 255) ? s565 : lerp565(row[x], s565, ta);
                    }
                }
                else
                {

                if constexpr (RAW_COPY)
                {
                    if (texel != tex.key)
                    {
                        row[x] = texel;
                    }
                }
                else
                {
                    int r, g, b, a;
                    bool visible = true;

                    if (FMT == 0)
                    {
                        if (texel == tex.key)
                        {
                            visible = false;
                            a = 0;
                        }
                        else
                        {
                            unpack565(texel, r, g, b);
                            a = 255;
                        }
                    }
                    else if (FMT == 1)
                    {
                        /* ARGB1555 是 5-5-5 布局（bit15=alpha），不能套用 RGB565 的 6 位绿解包 */
                        a = (texel & 0x8000u) ? 255 : 0;
                        visible = (a != 0);

                        int r5 = (texel >> 10) & 0x1F;
                        int g5 = (texel >> 5) & 0x1F;
                        int b5 = texel & 0x1F;

                        r = (r5 << 3) | (r5 >> 2);
                        g = (g5 << 3) | (g5 >> 2);
                        b = (b5 << 3) | (b5 >> 2);
                    }
                    else
                    {
                        int ta4 = (texel >> 12) & 0x0F;
                        a = (ta4 << 4) | ta4;
                        visible = (ta4 != 0);
                        r = ((texel >> 8) & 0x0F) * 17;
                        g = ((texel >> 4) & 0x0F) * 17;
                        b = (texel & 0x0F) * 17;
                    }

                    if (visible)
                    {
                        int ta = opacity;

                        /* ---- 色调 ---- */
                        if (COLMODE == 0)
                        {
                            if ((cr_c != 255) || (cg_c != 255) || (cb_c != 255))
                            {
                                r = mul255(r, cr_c);
                                g = mul255(g, cg_c);
                                b = mul255(b, cb_c);
                            }
                            ta = mul255(ta, (A->color >> 24) & 0xFF);
                        }
                        else
                        {
                            int taa = (int)ca;

                            if (taa < 0) { taa = 0; } else if (taa > 255) { taa = 255; }

                            if (COLMODE == 2)
                            {
                                int tr = (int)cr, tg = (int)cg, tb = (int)cb;

                                if (tr < 0) { tr = 0; } else if (tr > 255) { tr = 255; }
                                if (tg < 0) { tg = 0; } else if (tg > 255) { tg = 255; }
                                if (tb < 0) { tb = 0; } else if (tb > 255) { tb = 255; }

                                r = mul255(r, tr);
                                g = mul255(g, tg);
                                b = mul255(b, tb);
                            }
                            else if ((cr_c != 255) || (cg_c != 255) || (cb_c != 255))
                            {
                                r = mul255(r, cr_c);
                                g = mul255(g, cg_c);
                                b = mul255(b, cb_c);
                            }

                            ta = mul255(ta, taa);
                        }

                        if (a < 255)
                        {
                            ta = mul255(ta, a);
                        }

                        /* ---- 混合 ---- */
                        if (BLEND == 0)
                        {
                            if (ta >= 255)
                            {
                                row[x] = pack565(r, g, b);
                            }
                            else
                            {
                                row[x] = lerp565(row[x], pack565(r, g, b), ta);
                            }
                        }
                        else if (BLEND == 1)
                        {
                            row[x] = add565(row[x], pack565(r, g, b), ta);
                        }
                        else
                        {
                            row[x] = blend8<BLEND>(row[x], r, g, b, ta);
                        }
                    }
                }

                }   /* end of general 8-bit path */

                u += du_dx;
                v += dv_dx;

                if (COLMODE != 0)
                {
                    ca += da_dx;
                }
                if (COLMODE == 2)
                {
                    cr += dcrdx; cg += dcgdx; cb += dcbdx;
                }
            }
        }

        w0_row += dw0dy; w1_row += dw1dy; w2_row += dw2dy;
    }
}

/*----------------------------------------------------------------- 分派 */

R2D_AI bool pot_size(int w, int h)
{
    return ((w & (w - 1)) == 0) && ((h & (h - 1)) == 0);
}

R2D_AI bool same_rgb(uint32_t c0, uint32_t c1, uint32_t c2)
{
    return ((c0 & 0x00FFFFFFu) == (c1 & 0x00FFFFFFu)) && ((c0 & 0x00FFFFFFu) == (c2 & 0x00FFFFFFu));
}

template <int FMT, int BLEND, bool POT>
static void dispatch_colmode(const raster_surface_t *s, const raster_texture_t *t,
                             const raster_vertex_t *a, const raster_vertex_t *b,
                             const raster_vertex_t *c, uint8_t opacity)
{
    if ((a->color == b->color) && (a->color == c->color))
    {
        /* RAW_COPY 只对 RGB565 源成立：ARGB1555 必须走解包转换，不能直接写原始 texel */
        if ((BLEND == 0) && (FMT == 0) && (a->color == 0xFFFFFFFFu) && (opacity >= 255u))
        {
            raster_tri<FMT, BLEND, 0, POT, true>(s, t, a, b, c, opacity);
        }
        else
        {
            raster_tri<FMT, BLEND, 0, POT, false>(s, t, a, b, c, opacity);
        }
    }
    else if (same_rgb(a->color, b->color, c->color))
    {
        raster_tri<FMT, BLEND, 1, POT, false>(s, t, a, b, c, opacity);
    }
    else
    {
        raster_tri<FMT, BLEND, 2, POT, false>(s, t, a, b, c, opacity);
    }
}

template <int FMT, bool POT>
static void dispatch_blend(const raster_surface_t *s, const raster_texture_t *t,
                           const raster_vertex_t *a, const raster_vertex_t *b,
                           const raster_vertex_t *c, raster_blend_t blend, uint8_t opacity)
{
    switch (blend)
    {
        case RASTER_BLEND_ADD:      dispatch_colmode<FMT, 1, POT>(s, t, a, b, c, opacity); break;
        case RASTER_BLEND_MULTIPLY: dispatch_colmode<FMT, 2, POT>(s, t, a, b, c, opacity); break;
        case RASTER_BLEND_SCREEN:   dispatch_colmode<FMT, 3, POT>(s, t, a, b, c, opacity); break;
        default:                    dispatch_colmode<FMT, 0, POT>(s, t, a, b, c, opacity); break;
    }
}

template <int FMT>
static void dispatch_pot(const raster_surface_t *s, const raster_texture_t *t,
                         const raster_vertex_t *a, const raster_vertex_t *b,
                         const raster_vertex_t *c, raster_blend_t blend, uint8_t opacity)
{
    if (pot_size(t->w, t->h))
    {
        dispatch_blend<FMT, true>(s, t, a, b, c, blend, opacity);
    }
    else
    {
        dispatch_blend<FMT, false>(s, t, a, b, c, blend, opacity);
    }
}

extern "C" void raster_triangle(const raster_surface_t *s, const raster_texture_t *t,
                                const raster_vertex_t *v0, const raster_vertex_t *v1,
                                const raster_vertex_t *v2, raster_blend_t blend, uint8_t opacity)
{
    switch (t->fmt)
    {
        case RASTER_FMT_ARGB1555: dispatch_pot<1>(s, t, v0, v1, v2, blend, opacity); break;
        case RASTER_FMT_ARGB4444: dispatch_pot<2>(s, t, v0, v1, v2, blend, opacity); break;
        default:                  dispatch_pot<0>(s, t, v0, v1, v2, blend, opacity); break;
    }
}

extern "C" void raster_mesh(const raster_surface_t *s, const raster_texture_t *t,
                            const raster_vertex_t *verts, int nverts,
                            const uint16_t *indices, int nindices,
                            raster_blend_t blend, uint8_t opacity)
{
    (void)nverts;

    if ((indices == 0) || (nindices < 3))
    {
        return;
    }

    for (int i = 0; i + 2 < nindices; i += 3)
    {
        raster_triangle(s, t, &verts[indices[i]], &verts[indices[i + 1]],
                        &verts[indices[i + 2]], blend, opacity);
    }
}

extern "C" void raster_clear(const raster_surface_t *s, uint16_t color)
{
    for (int y = s->clip_y0; y <= s->clip_y1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        for (int x = s->clip_x0; x <= s->clip_x1; x++)
        {
            row[x] = color;
        }
    }
}

extern "C" void raster_flush(uint16_t *fb, int bytes)
{
    /* 交给平台层：H743 上是 SCB_CleanInvalidateDCache_by_Addr，
     * 无 D-Cache 的平台可以为空实现。 */
    plat_cache_clean(fb, (size_t)bytes);
}

extern "C" void raster_upscale2x(const uint16_t *src, int src_stride,
                                 uint16_t *dst, int dst_stride,
                                 int sx0, int sy0, int sx1, int sy1)
{
    int n = sx1 - sx0 + 1;

    if (n <= 0)
    {
        return;
    }

    /* 按"目标行"顺序写：每一行写完再写下一行，形成单条顺序写流。
     * 源行每个被读两次（r 和 r+1 对应同一源行），但源缓冲可 cache。 */
    for (int r = 2 * sy0; r <= 2 * sy1 + 1; r++)
    {
        const uint16_t *s = src + (size_t)(r >> 1) * src_stride + sx0;
        uint8_t        *dp = (uint8_t *)(dst + (size_t)r * dst_stride + 2 * sx0);
        int             i = 0;

        /* 8 字节对齐前缀（sx0 为奇数时 1 个源像素） */
        if ((((uintptr_t)dp) & 7u) != 0u)
        {
            uint16_t v = s[0];
            uint32_t vv = ((uint32_t)v << 16) | (uint32_t)v;

            *(uint32_t *)dp = vv;
            dp += 4;
            i = 1;

            if (i >= n)
            {
                continue;
            }
        }

        /* 主体：2 个源像素 -> 4 个输出像素 = 一次 64 位写 */
        int pairs = (n - i) >> 1;

        for (int k = 0; k < pairs; k++)
        {
            uint16_t a = s[i];
            uint16_t b = s[i + 1];
            /* 小端：低位 → 低地址。输出像素顺序必须是 a,a,b,b */
            uint64_t packed = (uint64_t)a | ((uint64_t)a << 16)
                            | ((uint64_t)b << 32) | ((uint64_t)b << 48);

            *(uint64_t *)dp = packed;
            dp += 8;
            i += 2;
        }

        /* 尾像素（n 为奇数时） */
        if (i < n)
        {
            uint16_t v = s[i];
            uint32_t vv = ((uint32_t)v << 16) | (uint32_t)v;

            *(uint32_t *)dp = vv;
        }
    }
}
