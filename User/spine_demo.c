/**
 ****************************************************************************************************
 * @file        spine_demo.c
 * @brief       Spine 运行时功能展示（循环播放，不返回）
 *
 * 依次演示：
 *   1. 双实例 + 不同动画 + tint
 *   2. 变换组合（翻转 / 缩放 / 透明度 / 着色）
 *   3. 重力方向旋转（物理形变）
 *   4. 动画巡演（枚举所有动画）
 *   5. 分辨率对比（全分辨率 vs 半分辨率）
 *   6. 压力测试（多实例）
 *
 * 屏幕顶部显示场景名，底部显示帧率与统计。
 ****************************************************************************************************
 */

#include "spine_demo.h"
#include "spine_api.h"
#include "plat/plat.h"


#include <stdio.h>
#include <string.h>

/* 板级帧缓冲指针（未在 ltdc.h 导出，这里自己声明，用于把 HUD 画进三块缓冲） */
extern uint32_t *g_ltdc_framebuf[2];
extern uint32_t  g_back_color;

#define DEMO_W          800
#define DEMO_H          480
#define DEMO_HUD_TOP    24
#define DEMO_HUD_BOT    24

/*----------------------------------------------------------------- HUD */

/* 覆盖层：走 spine_overlay_*，与 spine 层同一渲染目标。
 * 每帧在 spine_draw_begin() 与 spine_draw_end() 之间排队。 */
#define DEMO_SCENES   6

static char     s_hud_top[64];
static char     s_hud_bot[64];
static int      s_scene_now = 0;
static float    s_fps_now = 0.0f;
static float    s_prog_now = 0.0f;

static void demo_hud_queue(void)
{
    /* ---- 顶栏：6 个场景指示格 + 帧率条 + 场景名 ---- */
    spine_overlay_rect(0, 0, DEMO_W - 1, DEMO_HUD_TOP - 1, 0x0000);

    for (int k = 0; k < DEMO_SCENES; k++)
    {
        int cx = 8 + k * 26;

        spine_overlay_rect(cx, 5, cx + 20, 18,
                           (k == s_scene_now) ? (uint16_t)0xF800 : (uint16_t)0x2104);
    }

    {
        int w = (int)(s_fps_now * 4.0f);

        if (w > 292) { w = 292; }
        if (w < 0)   { w = 0; }

        /* 帧率条放底栏右侧，顶栏留给场景标题 */
        (void)w;
    }

    /* ---- 底栏：进度条 + 统计信息 ---- */
    spine_overlay_rect(0, DEMO_H - DEMO_HUD_BOT, DEMO_W - 1, DEMO_H - 1, 0x0000);

    {
        int w = (int)(s_prog_now * (float)(DEMO_W - 8));

        if (w > DEMO_W - 8) { w = DEMO_W - 8; }
        if (w < 0)          { w = 0; }

        spine_overlay_rect(4, DEMO_H - 4, 4 + w, DEMO_H - 2, 0x001F);

        {
            int fw = (int)(s_fps_now * 6.0f);

            if (fw > 220) { fw = 220; }
            if (fw < 0)   { fw = 0; }

            spine_overlay_rect(570, DEMO_H - 20, 790, DEMO_H - 8, 0x18E3);
            spine_overlay_rect(570, DEMO_H - 20, 570 + fw, DEMO_H - 8, 0x07E0);
        }
    }

    spine_overlay_text(180, 4, s_hud_top, 0xFFFF);   /* 避开左侧 6 个场景格 */
    spine_overlay_text(8, DEMO_H - DEMO_HUD_BOT + 1, s_hud_bot, 0x07FF);
}

static void demo_hud_set(const char *top, const char *bot)
{
    if (top != 0)
    {
        strncpy(s_hud_top, top, sizeof(s_hud_top) - 1);
        s_hud_top[sizeof(s_hud_top) - 1] = 0;
    }

    if (bot != 0)
    {
        strncpy(s_hud_bot, bot, sizeof(s_hud_bot) - 1);
        s_hud_bot[sizeof(s_hud_bot) - 1] = 0;
    }

    printf("[DEMO] %s | %s\r\n", s_hud_top, s_hud_bot);
}

/*----------------------------------------------------------------- 场景公共 */

static spine_asset_t *s_asset = 0;
static float s_fit = 1.0f;      /* 让角色高约 200 px 的缩放 */
static float s_cx = 0.0f;       /* 世界包围盒中心 */
static float s_cy = 0.0f;

static spine_instance_t *demo_make(const char *anim, float screen_cx, float screen_cy,
                                   float scale_mul, uint32_t tint, int flip_x, uint8_t alpha)
{
    spine_instance_t *in = spine_instance_create(s_asset);

    if (in == 0)
    {
        return 0;
    }

    if (anim != 0)
    {
        spine_instance_play(in, anim, 1, 0);
    }

    float s = s_fit * scale_mul;

    spine_instance_set_scale(in, s);
    spine_instance_set_position(in, screen_cx - s_cx * s, screen_cy - s_cy * s);

    if (flip_x)
    {
        spine_instance_set_flip(in, 1, 0);
    }

    if (tint != 0xFFFFFFFFu)
    {
        spine_instance_set_tint(in, tint);
    }

    if (alpha != 255)
    {
        spine_instance_set_alpha(in, alpha);
    }

    return in;
}

static void demo_destroy(spine_instance_t **list, int n)
{
    for (int i = 0; i < n; i++)
    {
        if (list[i] != 0)
        {
            spine_instance_destroy(list[i]);
            list[i] = 0;
        }
    }
}

/**
 * 跑若干帧，返回实际帧率。
 * @param frames  帧数
 * @param divisor 1=全分辨率 2=半分辨率
 * @param extra   每帧回调（可为空），用于场景自身的动态变化
 */
typedef void (*demo_tick_fn)(int frame, int frames);

static float demo_run_frames(spine_instance_t **list, int n, int frames, int divisor,
                             demo_tick_fn tick)
{
    uint32_t t0 = plat_now_ms();
    const float dt = 1.0f / 60.0f;

    for (int f = 0; f < frames; f++)
    {
        if (tick != 0)
        {
            tick(f, frames);
        }

        for (int i = 0; i < n; i++)
        {
            if (list[i] != 0)
            {
                spine_instance_update(list[i], dt);
            }
        }

        spine_draw_begin(divisor);

        for (int i = 0; i < n; i++)
        {
            if (list[i] != 0)
            {
                spine_instance_draw(list[i]);
            }
        }

        demo_hud_queue();           /* 覆盖层：与实例同一帧、同一渲染目标 */
        spine_draw_end();

        /* 每 30 帧更新一次 HUD 内容（绘制由 demo_hud_queue 每帧完成） */
        if ((f % 30) == 0)
        {
            uint32_t el = plat_now_ms() - t0;
            char buf[64];

            s_fps_now = (el > 0) ? (1000.0f * (float)(f + 1) / (float)el) : 0.0f;
            s_prog_now = (float)(f + 1) / (float)frames;

            snprintf(buf, sizeof(buf), "%s %.1fFPS %dINST",
                     (divisor == 1) ? "800X480" : "HALF", (double)s_fps_now, n);
            demo_hud_set(0, buf);
        }
    }

    uint32_t el = plat_now_ms() - t0;

    if (el == 0)
    {
        el = 1;
    }

    return 1000.0f * (float)frames / (float)el;
}

/*----------------------------------------------------------------- 场景 1：双实例 */

static void scene_duo(void)
{
    s_scene_now = 0;

    spine_instance_t *list[2];

    demo_hud_set("1/6 DUAL INST TINT", "loading...");

    list[0] = demo_make("swing",     210, 250, 1.0f, 0xFFFFFFFFu, 0, 255);
    list[1] = demo_make("wing-flap", 590, 250, 1.0f, 0xFFB0D0FFu, 0, 255);

    demo_run_frames(list, 2, 360, 2, 0);

    demo_destroy(list, 2);
}

/*----------------------------------------------------------------- 场景 2：变换组合 */

static void scene_transform(void)
{
    s_scene_now = 1;

    spine_instance_t *list[4];
    char buf[64];

    demo_hud_set("2/6 TRANSFORM DEMO", 0);

    list[0] = demo_make("wind-idle", 140, 250, 0.55f, 0xFFFFFFFFu, 0, 255);
    list[1] = demo_make("wind-idle", 330, 250, 0.55f, 0xFFFFFFFFu, 1, 255);
    list[2] = demo_make("wind-idle", 520, 250, 0.55f, 0xFFFFFFFFu, 0, 110);
    list[3] = demo_make("wind-idle", 710, 250, 0.55f, 0xFFFFC040u, 0, 255);

    {
        float fps = demo_run_frames(list, 4, 300, 2, 0);

        snprintf(buf, sizeof(buf), "%s | %.1f fps | 4 inst", "400x240(2x)", (double)fps);
        demo_hud_set(0, buf);
    }

    demo_destroy(list, 4);
}

/*----------------------------------------------------------------- 场景 3：重力旋转 */

static float s_gravity_t;

static void tick_gravity(int frame, int frames)
{
    float theta = 6.2831853f * 2.0f * (float)frame / (float)frames;

    (void)frames;
    s_gravity_t = theta;

    spine_world_set_gravity(cosf(theta), sinf(theta));
}

static void scene_gravity(void)
{
    s_scene_now = 2;

    spine_instance_t *list[2];
    char buf[80];

    demo_hud_set("3/6 GRAVITY ROTATE", 0);

    list[0] = demo_make("wind-idle", 300, 250, 1.0f, 0xFFFFFFFFu, 0, 255);
    list[1] = demo_make("wind-idle", 560, 250, 1.0f, 0xFFA0FFB0u, 0, 255);

    {
        float fps = demo_run_frames(list, 2, 420, 2, tick_gravity);

        snprintf(buf, sizeof(buf), "%s | %.1f fps | gravity %d deg",
                 "400x240(2x)", (double)fps, (int)(s_gravity_t * 57.2958f) % 360);
        demo_hud_set(0, buf);
    }

    spine_world_set_gravity(0.0f, 1.0f);        /* 复位 */
    demo_destroy(list, 2);
}

/*----------------------------------------------------------------- 场景 4：动画巡演 */

static void scene_anim_tour(void)
{
    s_scene_now = 3;

    int count = spine_asset_anim_count(s_asset);

    if (count > 6)
    {
        count = 6;                              /* 每个 3 秒，别太拖 */
    }

    for (int i = 0; i < count; i++)
    {
        const char *name = spine_asset_anim_name(s_asset, i);
        spine_instance_t *list[1];
        char top[64];

        snprintf(top, sizeof(top), "4/6 ANIM TOUR [%d/%d] %s", i + 1, count, name);
        demo_hud_set(top, 0);

        list[0] = demo_make(name, 400, 250, 1.0f, 0xFFFFFFFFu, 0, 255);

        demo_run_frames(list, 1, 180, 2, 0);
        demo_destroy(list, 1);
    }
}

/*----------------------------------------------------------------- 场景 5：分辨率对比 */

static void scene_resolution(void)
{
    s_scene_now = 4;

    spine_instance_t *list[4];
    char buf[96];
    float full, half;

    demo_hud_set("5/6 RES FULL VS HALF", 0);

    list[0] = demo_make("swing", 200, 250, 0.8f, 0xFFFFFFFFu, 0, 255);
    list[1] = demo_make("wing-flap", 400, 250, 0.8f, 0xFFB0D0FFu, 0, 255);
    list[2] = demo_make("swing", 600, 250, 0.8f, 0xFFFFC040u, 1, 255);
    list[3] = demo_make("wing-flap", 760, 250, 0.8f, 0xFFA0FFB0u, 0, 255);

    demo_hud_set(0, "800x480 full-res ...");
    full = demo_run_frames(list, 4, 180, 1, 0);

    demo_hud_set(0, "400x240 half-res ...");
    half = demo_run_frames(list, 4, 180, 2, 0);

    snprintf(buf, sizeof(buf), "full %.1f fps | half %.1f fps | %.2fx",
             (double)full, (double)half, (double)(half / full));
    demo_hud_set(0, buf);

    demo_destroy(list, 4);
}

/*----------------------------------------------------------------- 场景 6：压力测试 */

static void scene_stress(void)
{
    s_scene_now = 5;

    spine_instance_t *list[8];
    char buf[80];
    const char *anims[4] = { "swing", "wing-flap", "wind-idle", "stars" };
    float fps;

    demo_hud_set("6/6 STRESS 8 INST", 0);

    for (int i = 0; i < 8; i++)
    {
        float x = 90.0f + (float)i * 88.0f;

        list[i] = demo_make(anims[i & 3], x, 250, 0.45f, 0xFFFFFFFFu, (i & 1), 255);
    }

    fps = demo_run_frames(list, 8, 300, 2, 0);

    snprintf(buf, sizeof(buf), "%s | %.1f fps | 8 inst", "400x240(2x)", (double)fps);
    demo_hud_set(0, buf);

    demo_destroy(list, 8);
}

/*----------------------------------------------------------------- 入口 */

void spine_demo_run(void)
{
    printf("\r\n[DEMO] spine runtime showcase\r\n");

    plat_init();

    s_asset = spine_asset_load("/spine/celestial-circus-pro.skel",
                               "/spine/celestial-circus-pro.atlas");

    if (s_asset == 0)
    {
        printf("[DEMO] asset load failed\r\n");
        return;
    }

    printf("[DEMO] asset loaded, %d textures, %lu bytes\r\n",
           (int)0, (unsigned long)spine_asset_texture_bytes(s_asset));

    /* 用一次临时实例测出缩放与中心 */
    {
        spine_instance_t *tmp = spine_instance_create(s_asset);
        float x0 = 0, y0 = 0, x1 = 0, y1 = 0;

        if ((tmp != 0) && (spine_instance_get_bounds(tmp, &x0, &y0, &x1, &y1) != 0))
        {
            s_fit = 200.0f / (y1 - y0);
            s_cx = (x0 + x1) * 0.5f;
            s_cy = (y0 + y1) * 0.5f;
        }

        if (tmp != 0)
        {
            spine_instance_destroy(tmp);
        }
    }

    printf("[DEMO] fit scale=%.3f center=(%.1f, %.1f)\r\n",
           (double)s_fit, (double)s_cx, (double)s_cy);

    for (;;)
    {
        scene_duo();
        scene_transform();
        scene_gravity();
        scene_anim_tour();
        scene_resolution();
        scene_stress();

        demo_hud_set("=== LOOP END / RESTART ===", "2S");
        plat_delay_ms(2000);
    }
}
