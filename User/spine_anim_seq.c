/**
 ****************************************************************************************************
 * @file        spine_anim_seq.c
 * @brief       动画序列：walk(5s) -> idle(5s) -> aim(10s, 触摸驱动 aim-ik) -> death(5s, 单次)
 *
 * 用到的 API：
 *   spine_instance_set_default_mix()  段间过渡
 *   spine_instance_play()             切段
 *   spine_instance_set_ik_mix()       aim 段把 aim-ik 打开（该约束默认 mix=0）
 *   spine_instance_set_ik_target()    触摸驱动 IK 目标
 *   spine_instance_clear_ik()         离开 aim 段时还原
 ****************************************************************************************************
 */

#include "spine_anim_seq.h"
#include "spine_api.h"
#include "spine_touch.h"
#include "plat/plat.h"

#include <math.h>
#include <stdio.h>

#define SEQ_TAG "[SEQ] "
#define SEQ_NL  "\r\n"

/* 松手回复的时间常数（毫秒）：越小回得越快 */
#ifndef TEST_IK_RELEASE_TAU_MS
#define TEST_IK_RELEASE_TAU_MS  120
#endif

#define SEQ_MIX_SECONDS     0.30f
#define SEQ_TOUCH_TIMEOUT   120u        /* 超过这么久没有"按下"报文就当抬手 */
#define SEQ_RELEASE_BLEND   8


typedef struct
{
    const char *anim;
    int         loop;
    int         seconds;
    const char *ik;          /* 该段交互的 IK 名；NULL = 无 */
    const char *ik2;         /* 共用同一目标骨骼的第二个约束（一起淡入淡出） */
} seq_phase_t;

static const seq_phase_t g_phases[] =
{
    { "walk",  1,  5, 0,        0              },
    { "idle",  1,  5, 0,        0              },
    { "aim",   1, 10, "aim-ik", "aim-torso-ik" },   /* 两者共用同一个目标骨骼 */
    { "death", 0,  5, 0,        0              },
};

#define SEQ_PHASES  ((int)(sizeof(g_phases) / sizeof(g_phases[0])))

/*----------------------------------------------------------------- 触摸 -> IK（额外动作） */

/* aim-ik 平时 mix=0：只有触摸时把 mix 升起来，松手再降回去。
 * 与"接管现有 IK"（spine_ik_interactive.c 里腿那种）不同：
 * 这里不插值目标，只淡入淡出约束强度，部位自然回到动画姿态。 */
enum { SEQ_IK_IDLE = 0, SEQ_IK_FADE_IN, SEQ_IK_ACTIVE, SEQ_IK_FADE_OUT };

/* 1 = aim 段内自动模拟一次按压（第 2~6 秒），用于不触摸也能验证渐变 */
#ifndef SEQ_SIM_TOUCH
#define SEQ_SIM_TOUCH           1
#endif

#ifndef SEQ_IK_FADE_IN_MS
#define SEQ_IK_FADE_IN_MS       150     /* 按下时 mix 0 -> 1 用时 */
#endif

#ifndef SEQ_IK_FADE_OUT_MS
#define SEQ_IK_FADE_OUT_MS      250     /* 松手时 mix 1 -> 0 用时 */
#endif

typedef struct
{
    int      state;
    float    mix;               /* 当前 mix（我们自己维护，避免频繁读回） */
    float    t_state;           /* 进入当前状态后经过的秒数 */
    uint32_t last_press_ms;
    int      last_x, last_y;
} seq_ik_ctx_t;

static void seq_ik_reset(seq_ik_ctx_t *c)
{
    c->state = SEQ_IK_IDLE;
    c->mix = 0.0f;
    c->t_state = 0.0f;
    c->last_press_ms = 0;
}

/* 把屏幕坐标换算成骨架世界坐标 */
static void seq_screen_to_world(int mx, int my, float px, float py, float s,
                                float *wx, float *wy)
{
    *wx = ((float)mx - px) / s;
    *wy = ((float)my - py) / s;
}

int spine_anim_seq(const char *skel_path, const char *atlas_path)
{
    spine_asset_t *asset;
    spine_instance_t *in;
    float s = 1.0f, px = 0.0f, py = 0.0f;
    uint32_t t_prev;
    seq_ik_ctx_t ik;

    if ((skel_path == 0) || (atlas_path == 0))
    {
        return 0;
    }

    printf("\r\n" SEQ_TAG "asset: %s\r\n", skel_path);

    asset = spine_asset_load(skel_path, atlas_path);

    if (asset == 0)
    {
        printf(SEQ_TAG "load failed\r\n");
        return 0;
    }

    in = spine_instance_create(asset);

    if (in == 0)
    {
        spine_asset_free(asset);
        return 0;
    }

    printf(SEQ_TAG "touch init: %s\r\n", spine_touch_init() ? "OK" : "FAIL");

    spine_instance_set_default_mix(in, SEQ_MIX_SECONDS);
    seq_ik_reset(&ik);

    /* 摆到屏幕中央 */
    {
        float x0 = 0, y0 = 0, x1 = 0, y1 = 0;

        spine_instance_update(in, 0.0f);

        if (spine_instance_get_bounds(in, &x0, &y0, &x1, &y1) != 0)
        {
            float cx = (x0 + x1) * 0.5f;
            float cy = (y0 + y1) * 0.5f;
            float h = (y1 - y0);

            s = 360.0f / ((h > 1.0f) ? h : 400.0f);
            px = 400.0f - cx * s;
            py = 300.0f - cy * s;

            spine_instance_set_scale(in, s);
            spine_instance_set_position(in, px, py);
        }
    }

    t_prev = plat_now_ms();

    /* 首帧清屏（SDRAM 里可能留着上一轮的像素） */
    spine_draw_begin(2);
    spine_draw_force_full();
    spine_draw_end();

    for (int p = 0; p < SEQ_PHASES; p++)
    {
        const seq_phase_t *ph = &g_phases[p];
        uint32_t t_start = plat_now_ms();
        uint32_t t_last_report = t_start;

        spine_instance_play(in, ph->anim, ph->loop, 0);

        if (ph->ik != 0)
        {
            spine_instance_set_ik_mix(in, ph->ik, 0.0f);    /* 平时不参与 */

            if (ph->ik2 != 0)
            {
                spine_instance_set_ik_mix(in, ph->ik2, 0.0f);
            }
            seq_ik_reset(&ik);

            printf(SEQ_TAG "  %s 平时 mix=0，触摸时淡入" SEQ_NL, ph->ik);
        }

        {
            float dur = spine_instance_anim_duration(in, 0);

            printf(SEQ_TAG "phase %d/%d  %s  loop=%d  %d s  dur=%.2f%s%s" SEQ_NL,
                   p + 1, SEQ_PHASES, ph->anim, ph->loop, ph->seconds, (double)dur,
                   (ph->ik != 0) ? "  touch->" : "",
                   (ph->ik != 0) ? ph->ik : "");
        }
        for (;;)
        {
            uint32_t now = plat_now_ms();
            float dt = (float)(now - t_prev) / 1000.0f;
            char line[80];

            if ((dt <= 0.0f) || (dt > 0.1f))
            {
                dt = 1.0f / 60.0f;
            }

            t_prev = now;

            if ((now - t_start) >= (uint32_t)ph->seconds * 1000u)
            {
                break;
            }

/* ---- 该段的触摸 -> IK（mix 淡入淡出） ---- */
            if (ph->ik != 0)
            {
                unsigned short rx = 0, ry = 0;
                int got = spine_touch_poll(&rx, &ry);
                int pressed;

                if (got == 1)
                {
                    pressed = 1;
                    ik.last_press_ms = now;
                }
                else if (got == -1)
                {
                    pressed = 0;
                }
                else
                {
                    pressed = ((ik.last_press_ms != 0) &&
                               ((now - ik.last_press_ms) < SEQ_TOUCH_TIMEOUT)) ? 1 : 0;
                }

#if SEQ_SIM_TOUCH
                /* 第 2~6 秒模拟一次按压：目标绕圈，用于验证 mix 渐变 */
                {
                    uint32_t el = (now - t_start) / 1000u;

                    if ((el >= 2u) && (el < 6u))
                    {
                        float th = (float)(now - t_start - 2000u) / 1000.0f * 1.5f;

                        ik.last_x = 400 + (int)(cosf(th) * 120.0f);
                        ik.last_y = 200 + (int)(sinf(th) * 80.0f);
                        ik.last_press_ms = now;
                        pressed = 1;
                        got = 1;
                        rx = (unsigned short)ik.last_x;
                        ry = (unsigned short)ik.last_y;
                    }
                }
#endif

                ik.t_state += dt;

                if (pressed != 0)
                {
                    int mx = (got == 1) ? (int)rx : ik.last_x;
                    int my = (got == 1) ? (int)ry : ik.last_y;

                    if ((mx >= 0) && (mx < 800) && (my >= 0) && (my < 480))
                    {
                        float wx, wy;

                        seq_screen_to_world(mx, my, px, py, s, &wx, &wy);

                        if (spine_instance_set_ik_target(in, ph->ik, wx, wy) != 0)
                        {
                            ik.last_x = mx;
                            ik.last_y = my;

                            if (ik.state != SEQ_IK_ACTIVE)
                            {
                                if ((ik.state != SEQ_IK_FADE_IN) ||
                                    ((ik.mix > 0.0f) && (ik.state == SEQ_IK_IDLE)))
                                {
                                    printf(SEQ_TAG "  touch (%d,%d) -> world (%.1f,%.1f)" SEQ_NL,
                                           mx, my, (double)wx, (double)wy);
                                }

                                ik.state = SEQ_IK_FADE_IN;
                            }
                        }
                    }
                }

                /* mix 淡入 / 淡出 */
                if (ik.state == SEQ_IK_FADE_IN)
                {
                    ik.mix += dt * 1000.0f / (float)SEQ_IK_FADE_IN_MS;

                    if (ik.mix >= 1.0f)
                    {
                        ik.mix = 1.0f;
                        ik.state = SEQ_IK_ACTIVE;
                    }

                    spine_instance_set_ik_mix(in, ph->ik, ik.mix);
                }
                else if (ik.state == SEQ_IK_ACTIVE)
                {
                    if (pressed == 0)
                    {
                        ik.state = SEQ_IK_FADE_OUT;
                        ik.t_state = 0.0f;
                        printf(SEQ_TAG "  release -> mix 1 -> 0 (%d ms)" SEQ_NL,
                               SEQ_IK_FADE_OUT_MS);
                    }
                }
                else if (ik.state == SEQ_IK_FADE_OUT)
                {
                    ik.mix -= dt * 1000.0f / (float)SEQ_IK_FADE_OUT_MS;

                    if (ik.mix <= 0.0f)
                    {
                        ik.mix = 0.0f;
                        ik.state = SEQ_IK_IDLE;

                        spine_instance_set_ik_mix(in, ph->ik, 0.0f);
                        spine_instance_clear_ik(in);       /* 目标已无影响 */
                    }
                    else
                    {
                        spine_instance_set_ik_mix(in, ph->ik, ik.mix);
                    }
                }
                else if ((ik.state == SEQ_IK_IDLE) && (ik.mix != 0.0f))
                {
                    ik.mix = 0.0f;
                    spine_instance_set_ik_mix(in, ph->ik, 0.0f);
                }

                /* 每帧强制写一次：动画的 mix 时间轴会在 apply() 里覆盖，必须每帧夺回。
                 * 共用目标骨骼的第二个约束也要一起淡入淡出，否则它会立刻全量跟随。 */
                spine_instance_set_ik_mix(in, ph->ik, (ik.state == SEQ_IK_IDLE) ? 0.0f : ik.mix);

                if (ph->ik2 != 0)
                {
                    spine_instance_set_ik_mix(in, ph->ik2, (ik.state == SEQ_IK_IDLE) ? 0.0f : ik.mix);
                }
            }

            spine_instance_update(in, dt);

            /* ---- 渲染 ---- */
            spine_draw_begin(2);
            spine_instance_draw(in);

            {
                int left = ph->seconds - (int)((now - t_start) / 1000u);

                snprintf(line, sizeof(line), "%s %ds%s%s",
                         ph->anim, left,
                         (ph->loop != 0) ? "" : " once",
                         (ph->ik != 0) ? ((ik.state == SEQ_IK_ACTIVE) ? " TOUCH" : " TAP") : "");

                spine_overlay_rect(0, 0, 799, 23, 0x0000);
                spine_overlay_text(8, 3, line, 0xFFFF);
            }

            spine_draw_end();

            /* 每秒打一行 */
            if ((now - t_last_report) >= 1000u)
            {
                const char *cur = spine_instance_current_anim(in, 0);

                t_last_report = now;
                float atime = spine_instance_anim_time(in, 0);

                if (ph->ik != 0)
                {
                    float apx = 0, apy = 0;

                    spine_instance_get_ik_tip(in, ph->ik, &apx, &apy);

                    printf(SEQ_TAG "  t=%ds  mix=%.2f/%.2f  st=%d  tip=(%.0f,%.0f)  gt=0x%02X" SEQ_NL,
                           (int)((now - t_start) / 1000u),
                           (double)ik.mix,
                           (double)spine_instance_ik_mix_applied(in, ph->ik),
                           ik.state,
                           (double)apx, (double)apy,
                           (unsigned)spine_touch_status());
                }
                else
                printf(SEQ_TAG "  t=%ds  anim=%s  track=%.2f  applied=%.2f" SEQ_NL,
                       (int)((now - t_start) / 1000u),
                       (cur != 0) ? cur : "?",
                       (double)spine_instance_get_time(in, 0),
                       (double)atime);
            }
        }

        if (ph->ik != 0)
        {
            spine_instance_set_ik_mix(in, ph->ik, 0.0f);

            if (ph->ik2 != 0)
            {
                spine_instance_set_ik_mix(in, ph->ik2, 0.0f);
            }

            spine_instance_clear_ik(in);            /* 还原目标骨骼 */
        }
    }

    printf(SEQ_TAG "RESULT DONE\r\n");

    spine_instance_destroy(in);
    spine_asset_free(asset);

    return 1;
}
