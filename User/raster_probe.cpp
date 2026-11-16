/**
 ****************************************************************************************************
 * @file        raster_probe.cpp
 * @brief       最小自写光栅器原型（点采样纹理三角形）—— 用于验证"自写光栅能到多少 Mpx/s"
 * @note        只为测吞吐，不是生产实现：
 *                - 无裁剪（顶点需在屏幕内）、无边界规则（top-left）、POT 纹理直接取模
 *                - 三种模式：0=覆盖写, 1=色键透明(0x0000), 2=色键+常量色调
 *                - UV 用平面梯度（每三角形算一次），逐像素只做 2 次浮点加法
 ****************************************************************************************************
 */

#include <math.h>
#include "raster_probe.h"

extern "C"
{
#include "./BSP/LCD/lcd.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include <stdio.h>
}

#define SCR_W   800
#define SCR_H   480
#define FB_ADDR 0xC0000000u
#define TEX_W   64
#define TEX_H   64

static uint16_t *const s_fb = (uint16_t *)FB_ADDR;
static uint16_t        s_tex[TEX_W * TEX_H];

float g_raster_mpx = 0.0f;          /* 结果供界面显示 */

struct Vtx
{
    float x, y, u, v;
};

/*----------------------------------------------------------------- texture */
static void make_tex(void)
{
    for (int y = 0; y < TEX_H; y++)
    {
        for (int x = 0; x < TEX_W; x++)
        {
            int r = (x * 4) & 0x1F;
            int g = (y * 4) & 0x3F;
            int b = ((x ^ y) & 0x10) ? 0x1F : 0x04;

            /* 棋盘格留黑（色键测试用） */
            uint16_t c = (uint16_t)((r << 11) | (g << 5) | b);
            if ((((x >> 3) + (y >> 3)) & 1) != 0)
            {
                c = 0;
            }
            s_tex[y * TEX_W + x] = c;
        }
    }
}

/*----------------------------------------------------------------- raster */
/* MODE: 0 = opaque, 1 = colour key, 2 = colour key + constant tint */
template <int MODE>
static void draw_tri(const Vtx &A, const Vtx &B, const Vtx &C, uint16_t tint)
{
    const Vtx *p0 = &A, *p1 = &B, *p2 = &C, *tmp;

    if (p0->y > p1->y) { tmp = p0; p0 = p1; p1 = tmp; }
    if (p1->y > p2->y) { tmp = p1; p1 = p2; p2 = tmp; }
    if (p0->y > p1->y) { tmp = p0; p0 = p1; p1 = tmp; }

    float dy02 = p2->y - p0->y;
    if (dy02 <= 0.0f)
    {
        return;
    }

    /* 平面梯度：u(x,y) = u0 + du_dx*(x-x0) + du_dy*(y-y0) */
    float det = (p1->x - p0->x) * dy02 - (p2->x - p0->x) * (p1->y - p0->y);
    if (det == 0.0f)
    {
        return;
    }

    float du_dx = ((p1->u - p0->u) * dy02 - (p2->u - p0->u) * (p1->y - p0->y)) / det;
    float dv_dx = ((p1->v - p0->v) * dy02 - (p2->v - p0->v) * (p1->y - p0->y)) / det;
    float du_dy = ((p2->u - p0->u) * (p1->x - p0->x) - (p1->u - p0->u) * (p2->x - p0->x)) / det;
    float dv_dy = ((p2->v - p0->v) * (p1->x - p0->x) - (p1->v - p0->v) * (p2->x - p0->x)) / det;

    int ya = (int)ceilf(p0->y), yb = (int)floorf(p2->y);
    if (ya < 0) { ya = 0; }
    if (yb > SCR_H - 1) { yb = SCR_H - 1; }

    for (int y = ya; y <= yb; y++)
    {
        float fy = (float)y + 0.5f;

        /* 左边：p0->p2 */
        float k02 = (fy - p0->y) / dy02;
        float xl = p0->x + (p2->x - p0->x) * k02;

        /* 右边：上半段 p0->p1，下半段 p1->p2 */
        const Vtx *ra = (fy <= p1->y) ? p0 : p1;
        const Vtx *rb = (fy <= p1->y) ? p1 : p2;
        float dy_r = rb->y - ra->y;
        float xr = (dy_r > 0.0f) ? (ra->x + (rb->x - ra->x) * ((fy - ra->y) / dy_r)) : xl;

        if (xr < xl)
        {
            float t = xl; xl = xr; xr = t;
        }

        int xa = (int)ceilf(xl - 0.5f);
        int xb = (int)floorf(xr - 0.5f);
        if (xa < 0) { xa = 0; }
        if (xb > SCR_W - 1) { xb = SCR_W - 1; }
        if (xa > xb) { continue; }

        float u = p0->u + du_dx * ((float)xa + 0.5f - p0->x) + du_dy * (fy - p0->y);
        float v = p0->v + dv_dx * ((float)xa + 0.5f - p0->x) + dv_dy * (fy - p0->y);

        uint16_t *row = s_fb + y * SCR_W;

        for (int x = xa; x <= xb; x++)
        {
            int tx = ((int)u) & (TEX_W - 1);
            int ty = ((int)v) & (TEX_H - 1);
            uint16_t c = s_tex[(ty << 6) + tx];

            if (MODE == 0)
            {
                row[x] = c;
            }
            else if (MODE == 1)
            {
                if (c != 0u)
                {
                    row[x] = c;
                }
            }
            else
            {
                if (c != 0u)
                {
                    uint32_t r = ((c >> 11) & 0x1F) * ((tint >> 11) & 0x1F) >> 5;
                    uint32_t g = ((c >> 5) & 0x3F) * ((tint >> 5) & 0x3F) >> 6;
                    uint32_t b = (c & 0x1F) * (tint & 0x1F) >> 5;
                    row[x] = (uint16_t)((r << 11) | (g << 5) | b);
                }
            }

            u += du_dx;
            v += dv_dx;
        }
    }
}

/*----------------------------------------------------------------- benches */
static void dwt_setup(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0u;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static float mpx(uint32_t pixels, uint32_t cycles)
{
    return (cycles == 0u) ? 0.0f : ((float)pixels * 480.0f) / (float)cycles;
}

/* 全屏两三角形 */
template <int MODE>
static float bench_quad(uint32_t reps, uint16_t tint)
{
    Vtx p0 = { 0.0f, 0.0f, 0.0f, 0.0f };
    Vtx p1 = { (float)SCR_W, 0.0f, (float)TEX_W, 0.0f };
    Vtx p2 = { (float)SCR_W, (float)SCR_H, (float)TEX_W, (float)TEX_H };
    Vtx p3 = { 0.0f, (float)SCR_H, 0.0f, (float)TEX_H };
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        draw_tri<MODE>(p0, p1, p2, tint);
        draw_tri<MODE>(p0, p2, p3, tint);
    }

    return mpx((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

/* 16x12 网格（类 Spine：768 个三角形） */
template <int MODE>
static float bench_grid(uint32_t reps, uint16_t tint)
{
    const int   cols = 16, rows = 12;
    const float cw = (float)SCR_W / cols;
    const float ch = (float)SCR_H / rows;
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t r = 0; r < reps; r++)
    {
        for (int cy = 0; cy < rows; cy++)
        {
            for (int cx = 0; cx < cols; cx++)
            {
                float x0 = cx * cw, y0 = cy * ch;
                float x1 = x0 + cw, y1 = y0 + ch;

                Vtx a = { x0, y0, 0.0f, 0.0f };
                Vtx b = { x1, y0, (float)TEX_W, 0.0f };
                Vtx c = { x1, y1, (float)TEX_W, (float)TEX_H };
                Vtx d = { x0, y1, 0.0f, (float)TEX_H };

                draw_tri<MODE>(a, b, c, tint);
                draw_tri<MODE>(a, c, d, tint);
            }
        }
    }

    return mpx((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

/*----------------------------------------------------------------- entry */
extern "C" uint8_t raster_probe(void)
{
    float r_opaque, r_key, r_tint, r_grid, r_grid_tint;

    printf("\r\n[RASTR] minimal custom rasterizer probe\r\n");

    make_tex();
    dwt_setup();

    r_opaque = bench_quad<0>(4u, 0xFFFFu);
    r_key    = bench_quad<1>(4u, 0xFFFFu);
    r_tint   = bench_quad<2>(4u, 0xFFFFu);
    r_grid   = bench_grid<1>(2u, 0xFFFFu);
    r_grid_tint = bench_grid<2>(2u, 0xFFFFu);

    printf("[RASTR] quad opaque : %d.%02d Mpx/s\r\n", (int)r_opaque, (int)(r_opaque * 100.0f) % 100);
    printf("[RASTR] quad key    : %d.%02d Mpx/s\r\n", (int)r_key, (int)(r_key * 100.0f) % 100);
    printf("[RASTR] quad key+tint: %d.%02d Mpx/s\r\n", (int)r_tint, (int)(r_tint * 100.0f) % 100);
    printf("[RASTR] grid key    : %d.%02d Mpx/s  (16x12, 768 tris)\r\n",
           (int)r_grid, (int)(r_grid * 100.0f) % 100);
    printf("[RASTR] grid key+tint: %d.%02d Mpx/s\r\n",
           (int)r_grid_tint, (int)(r_grid_tint * 100.0f) % 100);

    g_raster_mpx = r_grid_tint;

    printf("[RASTR] RESULT %s\r\n",
           ((r_opaque > 0.0f) && (r_grid_tint > 0.0f)) ? "PASS" : "FAIL");

    return ((r_opaque > 0.0f) && (r_grid_tint > 0.0f)) ? 0u : 1u;
}
