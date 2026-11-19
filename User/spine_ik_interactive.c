/**
 ****************************************************************************************************
 * @file        spine_ik_interactive.c
 * @brief       触摸交互：点击屏幕 → 把点击位置换成骨架世界坐标 → 驱动 IK 目标
 ****************************************************************************************************
 */

#include "spine_ik_interactive.h"
#include "spine_api.h"
#include "plat/plat.h"

#include "./BSP/TOUCH/touch.h"
#include "./BSP/LCD/lcd.h"

#include <math.h>
#include <stdio.h>

#define IKT_TAG "[IKT] "

#include "test_cfg.h"

/* 触摸状态机 */
enum { IK_IDLE = 0, IK_ACTIVE, IK_BLEND };

/* 松手回复的时间常数（毫秒）：越小回得越快 */
#ifndef TEST_IK_RELEASE_TAU_MS
#define TEST_IK_RELEASE_TAU_MS  120
#endif

#ifndef IK_TOUCH_TIMEOUT_MS
#define IK_TOUCH_TIMEOUT_MS   120u      /* 超过这么久没有"按下"报文就当作抬手 */
#endif

/*----------------------------------------------------------------- GT1151 轮询
 *
 * 本板 PH7 被 SDRAM 占用（去掉就 SDRAM 自检失败），触摸 INT 不可用。
 * 直接读 GT1151 的状态/坐标寄存器，不依赖 INT 引脚。
 * 返回  1 = 按下（x/y 为 IC 原始坐标）
 *        0 = 无新报文（保持当前状态）
 *       -1 = 抬手
 */
#define GT_REG_STATUS   0x814Eu
#define GT_REG_PT0      0x8150u

static uint8_t g_gt_st = 0;

static int gt_poll(uint16_t *x, uint16_t *y)
{
    uint8_t st = 0;
    uint8_t buf[4] = { 0, 0, 0, 0 };
    uint8_t clr = 0;
    int n;

    gt9xxx_rd_reg(GT_REG_STATUS, &st, 1);
    g_gt_st = st;

    if ((st & 0x80u) == 0u)
    {
        return 0;                       /* 没有新数据 */
    }

    n = st & 0x0Fu;

    if (n > 0)
    {
        gt9xxx_rd_reg(GT_REG_PT0, buf, 4);
    }

    gt9xxx_wr_reg(GT_REG_STATUS, &clr, 1);   /* 清标志，否则 INT/缓冲一直挂着 */

    if (n == 0)
    {
        return -1;                      /* 抬手 */
    }

    *x = (uint16_t)(((uint16_t)buf[1] << 8) | buf[0]);
    *y = (uint16_t)(((uint16_t)buf[3] << 8) | buf[2]);

    return 1;
}

int spine_ik_interactive(const char *skel_path, const char *atlas_path,
                         const char *ik_name, int max_seconds)
{
    spine_asset_t *asset = 0;
    spine_instance_t *in = 0;
    float s = 1.0f;             /* 世界 -> 屏幕 缩放 */
    float px = 0.0f;            /* 实例位置（屏幕像素） */
    float py = 0.0f;
    int touched = 0;            /* 是否收到过触摸（用于 RESULT） */
    int last_x = 0;
    int last_y = 0;
    int state = IK_IDLE;
    int blend_k = 0;
    float blend_t = 0.0f;
    uint32_t last_press_ms = 0;
    float rel_wx = 0.0f, rel_wy = 0.0f;     /* 松开瞬间的覆盖点 */
    float anim_wx = 0.0f, anim_wy = 0.0f;   /* 松开瞬间的动画目标 */
    uint32_t t0 = 0;
    uint32_t t_prev = 0;
    uint16_t rx_last = 0, ry_last = 0;
    uint8_t  st_last = 0;
    uint16_t sta_last = 0;
    char line[64];

    if ((skel_path == 0) || (atlas_path == 0) || (ik_name == 0))
    {
        return 0;
    }

    /* max_seconds <= 0 表示永久运行 */

    printf("\r\n" IKT_TAG "loading %s\r\n", skel_path);

    asset = spine_asset_load(skel_path, atlas_path);

    if (asset == 0)
    {
        printf(IKT_TAG "load failed\r\n");
        return 0;
    }

    in = spine_instance_create(asset);

    if (in == 0)
    {
        spine_asset_free(asset);
        return 0;
    }

    /* 列出动画，便于确认选了哪个 */
    printf(IKT_TAG "animations:");
    for (int i = 0; i < spine_asset_anim_count(asset); i++)
    {
        printf(" %s", spine_asset_anim_name(asset, i));
    }
    printf("\r\n");

    /* 用 walk：有实际运动，才能从串口或画面看出更新 */
    {
        int played = 0;
        int cnt = spine_asset_anim_count(asset);

        for (int i = 0; i < cnt; i++)
        {
            const char *nm = spine_asset_anim_name(asset, i);

            if ((nm != 0) && (nm[0] == 'w') && (nm[1] == 'a') && (nm[2] == 'l'))
            {
                spine_instance_play(in, nm, 1, 0);
                printf(IKT_TAG "playing: %s\r\n", nm);
                played = 1;
                break;
            }
        }

        if ((played == 0) && (cnt > 0))
        {
            spine_instance_play(in, spine_asset_anim_name(asset, 0), 1, 0);
        }
    }

    /* ---- 摆到屏幕中央，记录变换以便反算世界坐标 ---- */
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

    printf(IKT_TAG "ik=%s  scale=%.4f  origin=(%.1f,%.1f)\r\n",
           ik_name, (double)s, (double)px, (double)py);
    printf(IKT_TAG "touch the screen to move the IK target (%d s)\r\n", max_seconds);

    t0 = plat_now_ms();
    t_prev = t0;
    uint32_t f = 0;

    /* 直接清三块帧缓冲：上电后 SDRAM 里可能还留着上一轮的像素，
     * 而正常渲染只重画脏矩形。这里不绕 API，确保干净。 */
    for (int b = 0; b < plat_fb_count(); b++)
    {
        uint32_t *p32 = (uint32_t *)plat_fb_addr(b);

        if (p32 != 0)
        {
            for (uint32_t i = 0; i < (800u * 480u) / 2u; i++)
            {
                p32[i] = 0x00000000u;
            }

            plat_cache_clean(p32, 800u * 480u * 2u);
        }
    }

    for (;;)
    {
        if (max_seconds > 0)
        {
            uint32_t el = plat_now_ms() - t0;

            if (el > (uint32_t)max_seconds * 1000u)
            {
                break;
            }
        }

        /* ---- 触摸状态机：IDLE / ACTIVE / BLEND ---- */
        {
            uint16_t rx = 0, ry = 0;
            int got = gt_poll(&rx, &ry);
            uint32_t now = plat_now_ms();
            int pressed;

            st_last = g_gt_st;

            if (got == 1)
            {
                pressed = 1;
                last_press_ms = now;
            }
            else if (got == -1)
            {
                pressed = 0;
            }
            else
            {
                /* 没有新报文：用超时兜底，避免报文间隔被误判成抬手 */
                pressed = ((last_press_ms != 0) &&
                           ((now - last_press_ms) < IK_TOUCH_TIMEOUT_MS)) ? 1 : 0;
            }

            if (pressed != 0)
            {
                int mx = (got == 1) ? (int)rx : last_x;
                int my = (got == 1) ? (int)ry : last_y;

                if ((mx >= 0) && (mx < 800) && (my >= 0) && (my < 480))
                {
                    float wx = ((float)mx - px) / s;
                    float wy = ((float)my - py) / s;

                    if (spine_instance_set_ik_target(in, ik_name, wx, wy) != 0)
                    {
                        if (state != IK_ACTIVE)
                        {
                            state = IK_ACTIVE;
                            printf(IKT_TAG "ACTIVE  touch (%d,%d) -> world (%.1f,%.1f)\r\n",
                                   mx, my, (double)wx, (double)wy);
                        }

                        touched = 1;
                        last_x = mx;
                        last_y = my;
                    }
                }
            }
            else if (state == IK_ACTIVE)
            {
                /* 刚松开：记下覆盖点，问出动画此刻的目标，开始混合 */
                rel_wx = ((float)last_x - px) / s;
                rel_wy = ((float)last_y - py) / s;

                spine_instance_clear_ik(in);
                spine_instance_update(in, 1.0f / 60.0f);        /* 让动画写回目标 */
                spine_instance_get_ik_target(in, ik_name, &anim_wx, &anim_wy);

                /* 立刻把覆盖恢复成触点，并且**本帧不渲染**：
                 * 否则这一帧会按动画姿态画一次，下一帧又跳回触点 —— 就是抽搐。 */
                spine_instance_set_ik_target(in, ik_name, rel_wx, rel_wy);

                blend_k = 0;
                blend_t = 0.0f;

                if (TEST_IK_RELEASE_BLEND > 0)
                {
                    state = IK_BLEND;
                    printf(IKT_TAG "BLEND   tau=%dms -> back to animation\r\n",
                           TEST_IK_RELEASE_TAU_MS);
                    continue;                   /* 丢掉这一帧，避免双跳变 */
                }

                state = IK_IDLE;
                printf(IKT_TAG "IDLE    animation resumed (instant)\r\n");
                continue;
            }
        }

        /* ---- 松开后的混合：指数平滑逼近动画目标 ---- */
        if (state == IK_BLEND)
        {
            float dt = 1.0f / 60.0f;

            if (t_prev != 0)
            {
                dt = (float)(plat_now_ms() - t_prev) / 1000.0f;

                if ((dt <= 0.0f) || (dt > 0.1f))
                {
                    dt = 1.0f / 60.0f;
                }
            }

            float a = 1.0f - expf(-dt * 1000.0f / (float)TEST_IK_RELEASE_TAU_MS);

            rel_wx += (anim_wx - rel_wx) * a;
            rel_wy += (anim_wy - rel_wy) * a;

            spine_instance_set_ik_target(in, ik_name, rel_wx, rel_wy);

            blend_t += dt;
            blend_k++;

            /* 残差已经足够小，或超时：直接交回动画，看不出来 */
            {
                float dx = anim_wx - rel_wx;
                float dy = anim_wy - rel_wy;

                if ((sqrtf(dx * dx + dy * dy) < 2.0f) || (blend_t > 0.6f))
                {
                    spine_instance_clear_ik(in);
                    state = IK_IDLE;
                    printf(IKT_TAG "IDLE    animation resumed (%d frames)\r\n", blend_k);
                }
            }
        }

        {
            uint32_t now = plat_now_ms();
            float dt = (float)(now - t_prev) / 1000.0f;

            if ((dt <= 0.0f) || (dt > 0.1f))
            {
                dt = 1.0f / 60.0f;     /* 首帧或卡顿：钳到 60 fps */
            }

            t_prev = now;
            spine_instance_update(in, dt);
        }

        spine_draw_begin(2);
        spine_instance_draw(in);

        /* 画布上不画准星：脏矩形渲染清不掉历史像素，会留下残影。
         * 触摸反馈放在顶栏（每帧整条重画）+ 角色的腿实际被拉动。 */

        {
            float wx = 0, wy = 0;

            spine_instance_get_ik_target(in, ik_name, &wx, &wy);

            if (touched != 0)
            {
                snprintf(line, sizeof(line), "%s T(%d,%d) W(%.0f,%.0f)",
                         ik_name, last_x, last_y, (double)wx, (double)wy);
            }
            else
            {
                snprintf(line, sizeof(line), "%s W(%.0f,%.0f) TAP THE SCREEN",
                         ik_name, (double)wx, (double)wy);
            }

            spine_overlay_rect(0, 0, 799, 23, 0x0000);
            spine_overlay_text(8, 3, line, 0xFFFF);
        }

        spine_draw_end();
        f++;

        /* 每 2 秒打一行，确认程序还活着（串口没输出时也能判断） */
        if (((f % 60) == 0) && (f != 0))
        {
            {
                float tipx = 0, tipy = 0;

                float bx0 = 0, by0 = 0, bx1 = 0, by1 = 0;

                spine_instance_get_ik_tip(in, ik_name, &tipx, &tipy);
                spine_instance_get_bounds(in, &bx0, &by0, &bx1, &by1);

                printf(IKT_TAG "%s t=%lus %.1ffps state=%s tip=(%.0f,%.0f)\r\n",
                       ik_name, (unsigned long)((plat_now_ms() - t0) / 1000u),
                       (double)((float)f / ((float)(plat_now_ms() - t0) / 1000.0f)),
                       (state == IK_ACTIVE) ? "ACTIVE" : ((state == IK_BLEND) ? "BLEND" : "IDLE"),
                       (double)tipx, (double)tipy);
            }
        }
    }

    printf(IKT_TAG "RESULT %s\r\n", (touched != 0) ? "PASS (touch received)" : "SKIP (no touch)");

    spine_instance_destroy(in);
    spine_asset_free(asset);

    return (touched != 0) ? 1 : -1;
}
