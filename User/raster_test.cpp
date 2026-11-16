/**
 ****************************************************************************************************
 * @file        raster_test.cpp
 * @brief       自写光栅器（raster2d）正确性回归 + 性能基准
 * @note        回归项：
 *                T1 覆盖完整性（两三角形拼四边形，内部不得有裂缝）
 *                T2 不重复混合（top-left 规则，共享对角线两侧亮度必须一致）
 *                T3 顶点出屏裁剪（不越界、不漏画）
 *                T4 逐顶点色调渐变单调
 *                T5 四种混合模式数值抽查
 *              基准项：四边形/网格 × {RGB565色键, ARGB4444} × {常量色, 逐顶点色}
 ****************************************************************************************************
 */

#include "./RASTER/raster2d.h"
#include "raster_test.h"

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
#define TEX     64

static uint16_t *const s_fb = (uint16_t *)FB_ADDR;
static uint16_t        s_tex565[TEX * TEX];
static uint16_t        s_tex4444[TEX * TEX];
static uint16_t        s_flat[TEX * TEX];
static uint16_t        s_tex1555[TEX * TEX];

static raster_surface_t s_surf;
static raster_texture_t s_t565, s_t4444, s_tflat, s_t1555;

float g_r2d_mpx = 0.0f;          /* 结果供界面显示 */

/*----------------------------------------------------------------- 准备 */
static void make_textures(void)
{
    for (int y = 0; y < TEX; y++)
    {
        for (int x = 0; x < TEX; x++)
        {
            int r = (x * 4) & 0x1F;
            int g = (y * 4) & 0x3F;
            int b = ((x ^ y) & 0x10) ? 0x1F : 0x04;

            s_tex565[y * TEX + x] = (uint16_t)((r << 11) | (g << 5) | b);

            /* ARGB4444：alpha 从左到右 15..0，右半边基本透明 */
            int a4 = 15 - (x / 5);
            if (a4 < 0) { a4 = 0; }
            s_tex4444[y * TEX + x] = (uint16_t)((a4 << 12) | ((r >> 1) << 8) | ((g >> 2) << 4) | (b >> 1));

            s_flat[y * TEX + x] = 0xF81Fu;

            {
                int a4_2 = 15 - (x / 5);

                s_tex1555[y * TEX + x] = (uint16_t)((((a4_2 >= 8) ? 1 : 0) << 15) | (r << 10) | (g << 5) | b);
            }      /* 纯品红，不透明 */
        }
    }
}

static void setup(void)
{
    s_surf.px = s_fb;
    s_surf.w = SCR_W;
    s_surf.h = SCR_H;
    s_surf.stride = SCR_W;
    s_surf.clip_x0 = 0;
    s_surf.clip_y0 = 0;
    s_surf.clip_x1 = SCR_W - 1;
    s_surf.clip_y1 = SCR_H - 1;

    s_t565.px = s_tex565;
    s_t565.w = TEX;
    s_t565.h = TEX;
    s_t565.stride = TEX;
    s_t565.fmt = RASTER_FMT_RGB565;
    s_t565.key = 0x0000;

    s_t4444.px = s_tex4444;
    s_t4444.w = TEX;
    s_t4444.h = TEX;
    s_t4444.stride = TEX;
    s_t4444.fmt = RASTER_FMT_ARGB4444;
    s_t4444.key = 0;

    s_tflat.px = s_flat;
    s_tflat.w = TEX;
    s_tflat.h = TEX;
    s_tflat.stride = TEX;
    s_tflat.fmt = RASTER_FMT_RGB565;
    s_tflat.key = 0xFFFF;      /* 不会命中 */

    s_t1555.px = s_tex1555;
    s_t1555.w = TEX;
    s_t1555.h = TEX;
    s_t1555.stride = TEX;
    s_t1555.fmt = RASTER_FMT_ARGB1555;
    s_t1555.key = 0;
}

static inline uint16_t at(int x, int y)
{
    return s_fb[y * SCR_W + x];
}

/*----------------------------------------------------------------- 回归 */

/* T1: 两三角形拼四边形，内部不得有未覆盖像素 */
static int test_coverage(void)
{
    raster_clear(&s_surf, 0x0000);

    raster_vertex_t a = { 10.0f, 10.0f, 0.0f, 0.0f, 0xFFFFFFFFu };
    raster_vertex_t b = { 790.0f, 10.0f, 64.0f, 0.0f, 0xFFFFFFFFu };
    raster_vertex_t c = { 790.0f, 470.0f, 64.0f, 64.0f, 0xFFFFFFFFu };
    raster_vertex_t d = { 10.0f, 470.0f, 0.0f, 64.0f, 0xFFFFFFFFu };

    raster_triangle(&s_surf, &s_tflat, &a, &b, &c, RASTER_BLEND_NORMAL, 255);
    raster_triangle(&s_surf, &s_tflat, &a, &c, &d, RASTER_BLEND_NORMAL, 255);

    /* 只看四边形内部（留 2px 边距）；期望全部为 0xF81F */
    int bad = 0;

    for (int y = 16; y < 464; y++)
    {
        for (int x = 16; x < 784; x++)
        {
            if (at(x, y) != 0xF81F)
            {
                bad++;
            }
        }
    }

    printf("  T1 coverage     : %d uncovered px  %s\r\n", bad, (bad == 0) ? "OK" : "FAIL");
    return (bad == 0) ? 0 : 1;
}

/* T2: top-left 规则 —— 加法混合下，对角线两侧亮度必须一致（无重复混合） */
static int test_no_double_blend(void)
{
    raster_clear(&s_surf, 0x0000);

    raster_vertex_t a = { 40.0f, 40.0f, 0.0f, 0.0f, 0x80FFFFFFu };
    raster_vertex_t b = { 760.0f, 40.0f, 64.0f, 0.0f, 0x80FFFFFFu };
    raster_vertex_t c = { 760.0f, 440.0f, 64.0f, 64.0f, 0x80FFFFFFu };
    raster_vertex_t d = { 40.0f, 440.0f, 0.0f, 64.0f, 0x80FFFFFFu };

    raster_triangle(&s_surf, &s_tflat, &a, &b, &c, RASTER_BLEND_ADD, 255);
    raster_triangle(&s_surf, &s_tflat, &a, &c, &d, RASTER_BLEND_ADD, 255);

    /* 沿对角线取若干点，比较左下与右上两侧的亮度是否一致 */
    int bad = 0;

    for (int i = 0; i < 40; i++)
    {
        int x = 100 + i * 15;
        int y = 100 + i * 8;
        uint16_t left = at(x - 6, y + 4);      /* 左下侧（三角形 ACD） */
        uint16_t right = at(x + 6, y - 4);     /* 右上侧（三角形 ABC） */

        if ((left == 0x0000) || (right == 0x0000) || (left != right))
        {
            bad++;
        }
    }

    printf("  T2 seam         : %d mismatched pairs  %s\r\n", bad, (bad == 0) ? "OK" : "FAIL");
    return (bad == 0) ? 0 : 1;
}

/* T3: 顶点大幅出屏，不得越界、且内部应被完全覆盖 */
static int test_clipping(void)
{
    raster_clear(&s_surf, 0x0000);

    raster_vertex_t a = { -300.0f, -200.0f, 0.0f, 0.0f, 0xFFFFFFFFu };
    raster_vertex_t b = { 1200.0f, -100.0f, 64.0f, 0.0f, 0xFFFFFFFFu };
    raster_vertex_t c = { 400.0f, 900.0f, 32.0f, 64.0f, 0xFFFFFFFFu };

    raster_triangle(&s_surf, &s_t565, &a, &b, &c, RASTER_BLEND_NORMAL, 255);

    int painted = 0;

    for (int y = 0; y < SCR_H; y++)
    {
        for (int x = 0; x < SCR_W; x++)
        {
            if (at(x, y) != 0x0000)
            {
                painted++;
            }
        }
    }

    /* 该三角形跨越屏幕；应有相当数量的像素被画到，且不能整屏涂满 */
    int ok = (painted > 20000) && (painted < SCR_W * SCR_H);

    printf("  T3 clip         : %d px painted  %s\r\n", painted, ok ? "OK" : "FAIL");
    return ok ? 0 : 1;
}

/* T4: 逐顶点色调 —— 左黑右白，沿 x 单调递增 */
static int test_vertex_color(void)
{
    raster_clear(&s_surf, 0x0000);

    raster_vertex_t a = { 0.0f, 100.0f, 0.0f, 0.0f, 0xFF000000u };   /* 黑 */
    raster_vertex_t b = { 800.0f, 100.0f, 64.0f, 0.0f, 0xFFFFFFFFu }; /* 白 */
    raster_vertex_t c = { 800.0f, 380.0f, 64.0f, 64.0f, 0xFFFFFFFFu };
    raster_vertex_t d = { 0.0f, 380.0f, 0.0f, 64.0f, 0xFF000000u };

    raster_triangle(&s_surf, &s_tflat, &a, &b, &c, RASTER_BLEND_NORMAL, 255);
    raster_triangle(&s_surf, &s_tflat, &a, &c, &d, RASTER_BLEND_NORMAL, 255);

    int prev = -1;
    int bad = 0;

    for (int x = 20; x < 780; x += 40)
    {
        uint16_t c0 = at(x, 240);
        int r = (c0 >> 11) & 0x1F;

        if ((prev >= 0) && (r < prev))
        {
            bad++;
        }
        prev = r;
    }

    printf("  T4 vtx colour   : %d non-monotonic  %s\r\n", bad, (bad == 0) ? "OK" : "FAIL");
    return (bad == 0) ? 0 : 1;
}

/* T5: 混合模式数值抽查（1x1 像素级） */
static int test_blend_modes(void)
{
    int bad = 0;

    raster_vertex_t a = { 0.0f, 0.0f, 0.0f, 0.0f, 0xFFFFFFFFu };
    raster_vertex_t b = { 20.0f, 0.0f, 1.0f, 0.0f, 0xFFFFFFFFu };
    raster_vertex_t c = { 20.0f, 20.0f, 1.0f, 1.0f, 0xFFFFFFFFu };

    raster_texture_t flat = s_t565;
    static uint16_t gray[4] = { 0x8410, 0x8410, 0x8410, 0x8410 };   /* 中灰 */
    flat.px = gray;
    flat.w = 2;
    flat.h = 2;
    flat.stride = 2;
    flat.key = 0xFFFF;      /* 不会命中 */

    /* multiply: 白 * 中灰 = 中灰 */
    raster_clear(&s_surf, 0xFFFF);
    raster_triangle(&s_surf, &flat, &a, &b, &c, RASTER_BLEND_MULTIPLY, 255);
    if (at(15, 5) != 0x8410) { bad++; }

    /* screen: 黑 ⊕ 中灰 = 中灰 */
    raster_clear(&s_surf, 0x0000);
    raster_triangle(&s_surf, &flat, &a, &b, &c, RASTER_BLEND_SCREEN, 255);
    if (at(15, 5) != 0x8410) { bad++; }

    /* add: 黑 + 中灰 = 中灰 */
    raster_clear(&s_surf, 0x0000);
    raster_triangle(&s_surf, &flat, &a, &b, &c, RASTER_BLEND_ADD, 255);
    if (at(15, 5) != 0x8410) { bad++; }

    /* normal: 覆盖 */
    raster_clear(&s_surf, 0x0000);
    raster_triangle(&s_surf, &flat, &a, &b, &c, RASTER_BLEND_NORMAL, 255);
    if (at(15, 5) != 0x8410) { bad++; }

    printf("  T5 blend modes  : %d wrong  %s\r\n", bad, (bad == 0) ? "OK" : "FAIL");
    return (bad == 0) ? 0 : 1;
}

/*----------------------------------------------------------------- 基准 */

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

struct Quad
{
    raster_vertex_t a, b, c, d;
};

static Quad quad_full(uint32_t color)
{
    Quad q;

    q.a.x = 0.0f;      q.a.y = 0.0f;      q.a.u = 0.0f;  q.a.v = 0.0f;  q.a.color = color;
    q.b.x = SCR_W;     q.b.y = 0.0f;      q.b.u = TEX;   q.b.v = 0.0f;  q.b.color = color;
    q.c.x = SCR_W;     q.c.y = SCR_H;     q.c.u = TEX;   q.c.v = TEX;   q.c.color = color;
    q.d.x = 0.0f;      q.d.y = SCR_H;     q.d.u = 0.0f;  q.d.v = TEX;   q.d.color = color;
    return q;
}

static Quad quad_full_vcol(void)
{
    Quad q = quad_full(0xFFFFFFFFu);

    q.a.color = 0xFFFFFFFFu;
    q.b.color = 0xFFFF8080u;
    q.c.color = 0xFF80FF80u;
    q.d.color = 0xFF8080FFu;
    return q;
}

static Quad quad_full_alpha(void)          /* RGB 恒定、仅 alpha 逐顶点变化（spine slot alpha） */
{
    Quad q = quad_full(0xFFFFFFFFu);

    q.a.color = 0xFFFFFFFFu;
    q.b.color = 0xCCFFFFFFu;
    q.c.color = 0x99FFFFFFu;
    q.d.color = 0x66FFFFFFu;
    return q;
}

static void draw_quad(const Quad &q, const raster_texture_t &tex, raster_blend_t blend)
{
    raster_triangle(&s_surf, &tex, &q.a, &q.b, &q.c, blend, 255);
    raster_triangle(&s_surf, &tex, &q.a, &q.c, &q.d, blend, 255);
}

static void draw_grid(const raster_texture_t &tex, int cols, int rows, bool vcol)
{
    float cw = (float)SCR_W / cols;
    float ch = (float)SCR_H / rows;

    for (int cy = 0; cy < rows; cy++)
    {
        for (int cx = 0; cx < cols; cx++)
        {
            float x0 = cx * cw, y0 = cy * ch;
            float x1 = x0 + cw, y1 = y0 + ch;

            raster_vertex_t a = { x0, y0, 0.0f, 0.0f, 0xFFFFFFFFu };
            raster_vertex_t b = { x1, y0, (float)TEX, 0.0f, vcol ? 0xFFFF8080u : 0xFFFFFFFFu };
            raster_vertex_t c = { x1, y1, (float)TEX, (float)TEX, vcol ? 0xFF80FF80u : 0xFFFFFFFFu };
            raster_vertex_t d = { x0, y1, 0.0f, (float)TEX, vcol ? 0xFF8080FFu : 0xFFFFFFFFu };

            raster_triangle(&s_surf, &tex, &a, &b, &c, RASTER_BLEND_NORMAL, 255);
            raster_triangle(&s_surf, &tex, &a, &c, &d, RASTER_BLEND_NORMAL, 255);
        }
    }
}

static void draw_grid_alpha(const raster_texture_t &tex, int cols, int rows)
{
    float cw = (float)SCR_W / cols;
    float ch = (float)SCR_H / rows;

    for (int cy = 0; cy < rows; cy++)
    {
        for (int cx = 0; cx < cols; cx++)
        {
            float x0 = cx * cw, y0 = cy * ch;
            float x1 = x0 + cw, y1 = y0 + ch;

            raster_vertex_t a = { x0, y0, 0.0f, 0.0f, 0xFFFFFFFFu };
            raster_vertex_t b = { x1, y0, (float)TEX, 0.0f, 0xD0FFFFFFu };
            raster_vertex_t c = { x1, y1, (float)TEX, (float)TEX, 0xA0FFFFFFu };
            raster_vertex_t d = { x0, y1, 0.0f, (float)TEX, 0x70FFFFFFu };

            raster_triangle(&s_surf, &tex, &a, &b, &c, RASTER_BLEND_NORMAL, 255);
            raster_triangle(&s_surf, &tex, &a, &c, &d, RASTER_BLEND_NORMAL, 255);
        }
    }
}

extern "C" uint8_t raster_test(void)
{
    int fails = 0;

    printf("\r\n[R2D] custom rasterizer: regression + benchmark\r\n");

    setup();
    make_textures();
    dwt_setup();

    fails += test_coverage();
    fails += test_no_double_blend();
    fails += test_clipping();
    fails += test_vertex_color();
    fails += test_blend_modes();

    /* ---- 基准 ---- */
    Quad qc = quad_full(0xFFFFFFFFu);
    Quad qv = quad_full_vcol();

    uint32_t px_frame = (uint32_t)SCR_W * SCR_H;

    uint32_t t0 = DWT->CYCCNT;
    for (int i = 0; i < 4; i++) { draw_quad(qc, s_t565, RASTER_BLEND_NORMAL); }
    float r565_const = mpx(px_frame * 4u, DWT->CYCCNT - t0);

    t0 = DWT->CYCCNT;
    for (int i = 0; i < 4; i++) { draw_quad(qv, s_t565, RASTER_BLEND_NORMAL); }
    float r565_vcol = mpx(px_frame * 4u, DWT->CYCCNT - t0);

    t0 = DWT->CYCCNT;
    for (int i = 0; i < 4; i++) { draw_quad(qv, s_t4444, RASTER_BLEND_NORMAL); }
    float r4444_vcol = mpx(px_frame * 4u, DWT->CYCCNT - t0);

    /* 诊断：把 4444 纹理做成全不透明，观察"分支混合"占了多少钱 */
    {
        static uint16_t flat4444[TEX * TEX];

        for (int i = 0; i < TEX * TEX; i++)
        {
            flat4444[i] = (uint16_t)(0xF000u | (s_tex4444[i] & 0x0FFFu));
        }

        raster_texture_t t_flat4444 = s_t4444;
        t_flat4444.px = flat4444;

        t0 = DWT->CYCCNT;
        for (int i = 0; i < 4; i++) { draw_quad(qv, t_flat4444, RASTER_BLEND_NORMAL); }
        float r4444_op = mpx(px_frame * 4u, DWT->CYCCNT - t0);

        printf("[R2D] quad 4444 opaque: %d.%02d Mpx/s\r\n", (int)r4444_op, (int)(r4444_op * 100.0f) % 100);
    }

    {
        Quad qa = quad_full_alpha();
        Quad qc2 = quad_full(0xFF808080u);

        t0 = DWT->CYCCNT;
        for (int i = 0; i < 4; i++) { draw_quad(qc2, s_t565, RASTER_BLEND_NORMAL); }
        float r_const_tint = mpx(px_frame * 4u, DWT->CYCCNT - t0);

        t0 = DWT->CYCCNT;
        for (int i = 0; i < 4; i++) { draw_quad(qa, s_t4444, RASTER_BLEND_NORMAL); }
        float r_alpha_only = mpx(px_frame * 4u, DWT->CYCCNT - t0);

        t0 = DWT->CYCCNT;
        for (int i = 0; i < 2; i++) { draw_grid_alpha(s_t4444, 16, 12); }
        float r_grid_alpha = mpx(px_frame * 2u, DWT->CYCCNT - t0);

        /* g_r2d_mpx 已在 alpha-only 基准中赋值 */

		printf("[R2D] quad 565 const tint : %d.%02d Mpx/s\r\n", (int)r_const_tint, (int)(r_const_tint * 100.0f) % 100);
		printf("[R2D] quad 4444 alpha-only: %d.%02d Mpx/s\r\n", (int)r_alpha_only, (int)(r_alpha_only * 100.0f) % 100);
		printf("[R2D] grid 4444 alpha-only: %d.%02d Mpx/s\r\n", (int)r_grid_alpha, (int)(r_grid_alpha * 100.0f) % 100);
        g_r2d_mpx = r_grid_alpha;   /* 界面显示用：最具代表性的 spine 负载 */
    }

    t0 = DWT->CYCCNT;
    for (int i = 0; i < 2; i++) { draw_grid(s_t565, 16, 12, true); }
    float r_grid565 = mpx(px_frame * 2u, DWT->CYCCNT - t0);

    Quad qc2b = quad_full(0xFF808080u);

    t0 = DWT->CYCCNT;
    for (int i = 0; i < 4; i++) { draw_quad(qc2b, s_t1555, RASTER_BLEND_NORMAL); }
    float r1555_const = mpx(px_frame * 4u, DWT->CYCCNT - t0);

    t0 = DWT->CYCCNT;
    for (int i = 0; i < 2; i++) { draw_grid(s_t1555, 16, 12, true); }
    float r1555_grid = mpx(px_frame * 2u, DWT->CYCCNT - t0);

    printf("[R2D] quad 1555 const tint: %d.%02d Mpx/s\r\n", (int)r1555_const, (int)(r1555_const * 100.0f) % 100);
    printf("[R2D] grid 1555 vcol      : %d.%02d Mpx/s\r\n", (int)r1555_grid, (int)(r1555_grid * 100.0f) % 100);
    g_r2d_mpx = r1555_grid;     /* 界面显示：ARGB1555 逐顶点（推荐配置） */

    t0 = DWT->CYCCNT;
    for (int i = 0; i < 2; i++) { draw_grid(s_t4444, 16, 12, true); }
    float r_grid4444 = mpx(px_frame * 2u, DWT->CYCCNT - t0);

    printf("[R2D] quad 565 const : %d.%02d Mpx/s\r\n", (int)r565_const, (int)(r565_const * 100.0f) % 100);
    printf("[R2D] quad 565 vcol  : %d.%02d Mpx/s\r\n", (int)r565_vcol, (int)(r565_vcol * 100.0f) % 100);
    printf("[R2D] quad 4444 vcol : %d.%02d Mpx/s\r\n", (int)r4444_vcol, (int)(r4444_vcol * 100.0f) % 100);
    printf("[R2D] grid 565 vcol  : %d.%02d Mpx/s\r\n", (int)r_grid565, (int)(r_grid565 * 100.0f) % 100);
    printf("[R2D] grid 4444 vcol : %d.%02d Mpx/s\r\n", (int)r_grid4444, (int)(r_grid4444 * 100.0f) % 100);


    printf("[R2D] RESULT %s (regressions %d)\r\n", (fails == 0) ? "PASS" : "FAIL", fails);

    return (fails == 0) ? 0u : 1u;
}
