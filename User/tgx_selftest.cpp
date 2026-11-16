/**
 ****************************************************************************************************
 * @file        tgx_selftest.cpp
 * @brief       TGX 2D 渲染自检 + 吞吐基准（Cortex-M7 @480 MHz，帧缓冲在 SDRAM）
 * @note        1) 直接用真实帧缓冲 0xC0000000 绘制，验证 TGX 与 LTDC/SDRAM 打通
 *              2) 用 DWT 周期计数实测：纯填充率、纹理四边形、大量小三角形（类 Spine）
 *              3) 结果既画在屏幕上，也从串口输出
 *
 *  注意：SDRAM 被 MPU 配成 cacheable，绘制结束必须 clean/invalidate D-Cache，
 *        否则 LTDC 扫描到的是旧数据（花屏/不刷新）。
 ****************************************************************************************************
 */

#include "./TGX/tgx.h"
#include "tgx_selftest.h"
#include "raster_probe.h"
#include "raster_test.h"

extern "C"
{
#include "./BSP/LCD/lcd.h"
#include "./BSP/LCD/ltdc.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include <stdio.h>
#include <string.h>
}

using namespace tgx;

#define SCR_W       800
#define SCR_H       480
#define FB_ADDR     0xC0000000u
#define FB_BYTES    (SCR_W * SCR_H * 2)
#define MHZ         480.0f

static RGB32 s_tex[128 * 128];          /* 64 KB 纹理（AXI SRAM，非 cache 争用区） */

/*--------------------------------------------------------------- helpers */
static void dwt_setup(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0u;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static void fb_flush(void)
{
    SCB_CleanInvalidateDCache_by_Addr((uint32_t *)FB_ADDR, FB_BYTES);
}

/* pixels per second -> Mpx/s ; cycles at 480 MHz */
static float mpx_rate(uint32_t pixels, uint32_t cycles)
{
    if (cycles == 0u)
    {
        return 0.0f;
    }
    /* (pixels / (cycles/480e6)) / 1e6 = pixels * 480 / cycles */
    return ((float)pixels * MHZ) / (float)cycles;
}

static void make_texture(void)
{
    for (int y = 0; y < 128; y++)
    {
        for (int x = 0; x < 128; x++)
        {
            int r = (x * 2) & 0xFF;
            int g = (y * 2) & 0xFF;
            int b = ((x ^ y) & 0x20) ? 0xE0 : 0x20;
            int a = ((((x >> 3) + (y >> 3)) & 1) != 0) ? 0x80 : 0xFF;   /* 棋盘 alpha */

            s_tex[y * 128 + x] = RGB32(r, g, b, a);
        }
    }
}

/*--------------------------------------------------------------- benchmarks */
static float bench_fill(Image<RGB565> &dst, uint32_t reps)
{
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        dst.fillScreen(((i & 1u) != 0u) ? RGB565_Black : RGB565_Blue);
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

static float bench_texquad(Image<RGB565> &dst, Image<RGB32> &src, uint32_t reps)
{
    fVec2 s0(0, 0), s1(128, 0), s2(128, 128), s3(0, 128);
    fVec2 d0(0, 0), d1(SCR_W, 0), d2(SCR_W, SCR_H), d3(0, SCR_H);
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        dst.drawTexturedQuad(src, s0, s1, s2, s3, d0, d1, d2, d3, 1.0f);
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

/* 类 Spine 负载：16x12 个格子，每格 2 个带顶点色渐变的纹理三角形 */
static float bench_tris(Image<RGB565> &dst, Image<RGB32> &src, uint32_t reps)
{
    const int   cols = 16;
    const int   rows = 12;
    const float cw = (float)SCR_W / cols;
    const float ch = (float)SCR_H / rows;
    const fVec2 t0p(0, 0), t1p(128, 0), t2p(128, 128), t3p(0, 128);
    const RGB32 c1(255, 255, 255, 160);
    const RGB32 c2(255, 128, 128, 160);
    const RGB32 c3(128, 255, 255, 160);
    const RGB32 c4(128, 128, 255, 160);
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t r = 0; r < reps; r++)
    {
        for (int cy = 0; cy < rows; cy++)
        {
            for (int cx = 0; cx < cols; cx++)
            {
                float x0 = cx * cw, y0 = cy * ch;
                float x1 = x0 + cw, y1 = y0 + ch;

                fVec2 p0(x0, y0), p1(x1, y0), p2(x1, y1), p3(x0, y1);

                dst.drawTexturedGradientTriangle(src, t0p, t1p, t2p, p0, p1, p2, c1, c2, c3);
                dst.drawTexturedGradientTriangle(src, t0p, t2p, t3p, p0, p2, p3, c1, c3, c4);
            }
        }
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

/*--------------------------------------------------------------- matrix bench */
static RGB565 s_tex565[128 * 128];      /* 32 KB, no alpha */

static void make_texture565(void)
{
    for (int y = 0; y < 128; y++)
    {
        for (int x = 0; x < 128; x++)
        {
            s_tex565[y * 128 + x] = RGB565((x * 2) & 0xFF, (y * 2) & 0xFF,
                                           (((x ^ y) & 0x20) ? 0xE0 : 0x20));
        }
    }
}

static float bench_quad_generic(Image<RGB565> &dst, const Image<RGB32> &src32,
                                const Image<RGB565> &src565, int variant, uint32_t reps)
{
    fVec2 s0(0, 0), s1(128, 0), s2(128, 128), s3(0, 128);
    fVec2 d0(0, 0), d1(SCR_W, 0), d2(SCR_W, SCR_H), d3(0, SCR_H);
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        switch (variant)
        {
            case 0:   /* RGB565 source, overwrite */
                dst.drawTexturedQuad(src565, s0, s1, s2, s3, d0, d1, d2, d3, TGX_DEFAULT_NO_BLENDING);
                break;
            case 1:   /* RGB32 source, overwrite */
                dst.drawTexturedQuad(src32, s0, s1, s2, s3, d0, d1, d2, d3, TGX_DEFAULT_NO_BLENDING);
                break;
            default:  /* RGB32 source, alpha blend */
                dst.drawTexturedQuad(src32, s0, s1, s2, s3, d0, d1, d2, d3, 1.0f);
                break;
        }
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

static RGB565 s_tex64[64 * 64];         /* 8 KB: fits in the 16 KB D-cache */

static void make_texture64(void)
{
    for (int y = 0; y < 64; y++)
    {
        for (int x = 0; x < 64; x++)
        {
            s_tex64[y * 64 + x] = RGB565((x * 4) & 0xFF, (y * 4) & 0xFF,
                                         (((x ^ y) & 0x10) ? 0xE0 : 0x20));
        }
    }
}

/* same full-screen quad, but sampling an 8 KB texture */
static float bench_quad_small_tex(Image<RGB565> &dst, const Image<RGB565> &src, uint32_t reps)
{
    fVec2 s0(0, 0), s1(64, 0), s2(64, 64), s3(0, 64);
    fVec2 d0(0, 0), d1(SCR_W, 0), d2(SCR_W, SCR_H), d3(0, SCR_H);
    uint32_t t0 = DWT->CYCCNT;

    for (uint32_t i = 0; i < reps; i++)
    {
        dst.drawTexturedQuad(src, s0, s1, s2, s3, d0, d1, d2, d3, TGX_DEFAULT_NO_BLENDING);
    }

    return mpx_rate((uint32_t)SCR_W * SCR_H * reps, DWT->CYCCNT - t0);
}

/*--------------------------------------------------------------- demo screen */
static void draw_demo(Image<RGB565> &dst, Image<RGB32> &src,
                      float fill_rate, float tex_rate, float tri_rate)
{
    static const RGB565 bars[8] =
    {
        RGB565(255, 255, 255), RGB565(255, 255, 0), RGB565(0, 255, 255), RGB565(0, 255, 0),
        RGB565(255, 0, 255),   RGB565(255, 0, 0),   RGB565(0, 0, 255),   RGB565(0, 0, 0)
    };
    char line[96];

    /* 背景：竖向渐变（走逐像素颜色路径） */
    dst.fillScreenVGradient(RGB565((uint16_t)0x0821), RGB565((uint16_t)0x2104));

    for (int i = 0; i < 8; i++)
    {
        dst.fillRect(iBox2(i * 100, i * 100 + 99, 0, 40), bars[i]);
    }

    /* 纹理四边形（右上） */
    dst.drawTexturedQuad(src, fVec2(0, 0), fVec2(128, 0), fVec2(128, 128), fVec2(0, 128),
                         fVec2(520, 50), fVec2(780, 50), fVec2(780, 310), fVec2(520, 310), 1.0f);

    /* 抗锯齿图形 */
    dst.fillCircleAA(fVec2(150, 200), 60.0f, RGB565_Yellow, 1.0f);
    dst.drawThickLineAA(fVec2(40, 330), fVec2(460, 420), 6.0f, END_ROUNDED, END_ROUNDED,
                        RGB565_Cyan, 1.0f);
    dst.drawThickRectAA(fBox2(60.0f, 440.0f, 80.0f, 300.0f), 3.0f, RGB565_White, 1.0f);

    /* 屏幕文字（用 LCD 字库，TGX 内置字库已裁剪掉） */
    /* --- cache/coherency: flush CPU pixels BEFORE any DMA2D fill, then
     * drop stale lines so the CPU sees what DMA2D wrote (see docs §cache) --- */
    fb_flush();
    lcd_fill(20, 332, 780, 336, 0x07FF);   /* thin separator line (DMA2D) */
    SCB_InvalidateDCache_by_Addr((uint32_t *)FB_ADDR, FB_BYTES);

    g_back_color = 0x0000u;

    sprintf(line, "TGX 2D subset on STM32H743  (AC6 -O2, FPGA-free)");
    lcd_show_string(20, 350, 780, 16, 16, line, 0xFFFFu);
    sprintf(line, "fill   : %d.%02d Mpx/s", (int)fill_rate, (int)(fill_rate * 100.0f) % 100);
    lcd_show_string(20, 370, 780, 16, 16, line, 0xFFE0u);
    sprintf(line, "texquad: %d.%02d Mpx/s  (bilinear + alpha)", (int)tex_rate, (int)(tex_rate * 100.0f) % 100);
    lcd_show_string(20, 390, 780, 16, 16, line, 0xFFE0u);
    sprintf(line, "tris   : %d.%02d Mpx/s  (16x12 grid, gradient)", (int)tri_rate, (int)(tri_rate * 100.0f) % 100);
    lcd_show_string(20, 410, 780, 16, 16, line, 0xFFE0u);
    sprintf(line, "framebuffer @ 0x%08lX  %dx%d RGB565", (unsigned long)FB_ADDR, SCR_W, SCR_H);
    lcd_show_string(20, 432, 780, 16, 16, line, 0x07FFu);

    if (g_raster_mpx > 0.0f)
    {
        sprintf(line, "RASTR: %d.%02d Mpx/s (proto)", (int)g_raster_mpx, (int)(g_raster_mpx * 100.0f) % 100);
        lcd_show_string(20, 452, 380, 16, 16, line, 0xFFFFu);

        sprintf(line, "R2D: %d.%02d Mpx/s (prod, ARGB1555)", (int)g_r2d_mpx, (int)(g_r2d_mpx * 100.0f) % 100);
        lcd_show_string(410, 452, 390, 16, 16, line, 0xFFFFu);
    }

    fb_flush();
}

/*--------------------------------------------------------------- entry */
extern "C" uint8_t tgx_selftest(void)
{
    Image<RGB565> dst((uint16_t *)FB_ADDR, SCR_W, SCR_H);
    Image<RGB32>  src((RGB32 *)s_tex, 128, 128);
    float fill_rate, tex_rate, tri_rate;

    printf("\r\n[TGX] 2D render self-test, framebuffer @ 0x%08lX\r\n", (unsigned long)FB_ADDR);

    if (!dst.isValid() || !src.isValid())
    {
        printf("[TGX] image setup FAILED\r\n");
        return 1u;
    }

    make_texture();
    dwt_setup();

    printf("[TGX] benchmarking...\r\n");

    fill_rate = bench_fill(dst, 10u);
    tex_rate  = bench_texquad(dst, src, 4u);
    tri_rate  = bench_tris(dst, src, 2u);

    printf("[TGX] fill   : %d.%02d Mpx/s  (800x480 x10)\r\n",
           (int)fill_rate, (int)(fill_rate * 100.0f) % 100);
    printf("[TGX] texquad: %d.%02d Mpx/s  (800x480 x4, bilinear+alpha)\r\n",
           (int)tex_rate, (int)(tex_rate * 100.0f) % 100);
    printf("[TGX] tris   : %d.%02d Mpx/s  (16x12 grid, gradient triangles)\r\n",
           (int)tri_rate, (int)(tri_rate * 100.0f) % 100);

    {
        Image<RGB565> src565((RGB565 *)s_tex565, 128, 128);
        float r0, r1, r2;

        make_texture565();
        r0 = bench_quad_generic(dst, src, src565, 0, 4u);
        r1 = bench_quad_generic(dst, src, src565, 1, 4u);
        r2 = bench_quad_generic(dst, src, src565, 2, 4u);

        printf("[TGX] 565/ow : %d.%02d Mpx/s\r\n", (int)r0, (int)(r0 * 100.0f) % 100);
        printf("[TGX] 32/ow  : %d.%02d Mpx/s\r\n", (int)r1, (int)(r1 * 100.0f) % 100);
        printf("[TGX] 32/blend: %d.%02d Mpx/s\r\n", (int)r2, (int)(r2 * 100.0f) % 100);

        {
            Image<RGB565> small((RGB565 *)s_tex64, 64, 64);
            float r3;

            make_texture64();
            r3 = bench_quad_small_tex(dst, small, 4u);
            printf("[TGX] 565 8KB : %d.%02d Mpx/s  (texture fits in D-cache)\r\n",
                   (int)r3, (int)(r3 * 100.0f) % 100);
        }
    }

    /* 帧预算：60 fps = 16.7 ms；按 tris 吞吐换算可覆盖的像素数 */
    {
        float budget_px = tri_rate * 16667.0f;      /* Mpx/s * ms = kpx ... 见下 */

        /* tri_rate [Mpx/s] * 16.667 [ms] = 16.667 * Mpx/s * 1e6 / 1e3 = kpx */
        budget_px = tri_rate * 16.667f * 1000.0f;

        printf("[TGX] 60 fps budget @ tris rate: %d kpx per frame\r\n", (int)budget_px);
        printf("[TGX] 30 fps budget @ tris rate: %d kpx per frame\r\n",
               (int)(tri_rate * 33.333f * 1000.0f));
    }

    /* custom rasterizer prototype: same framebuffer, same load */
    (void)raster_probe();
    (void)raster_test();

    draw_demo(dst, src, fill_rate, tex_rate, tri_rate);

    printf("[TGX] RESULT %s\r\n",
           ((fill_rate > 0.0f) && (tex_rate > 0.0f) && (tri_rate > 0.0f)) ? "PASS" : "FAIL");

    return ((fill_rate > 0.0f) && (tex_rate > 0.0f) && (tri_rate > 0.0f)) ? 0u : 1u;
}
