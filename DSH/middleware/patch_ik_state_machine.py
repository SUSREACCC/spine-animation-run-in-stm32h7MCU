#!/usr/bin/env python3
"""Interactive IK: touch state machine (IDLE / ACTIVE / BLEND).

Replaces the old latch-forever `touched` logic:
  * IDLE   - no override at all, the animation drives the IK target
  * ACTIVE - while pressed, override the target with the finger position
  * BLEND  - after release, lerp the override back to the animation target
             for N frames, then clear it and return to IDLE
"""
import io

P = "User/spine_ik_interactive.c"

NEW_BLOCK = '''        /* ---- 触摸状态机：IDLE / ACTIVE / BLEND ---- */
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
                            printf(IKT_TAG "ACTIVE  touch (%d,%d) -> world (%.1f,%.1f)\\r\\n",
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

                blend_k = 0;

                if (TEST_IK_RELEASE_BLEND > 0)
                {
                    state = IK_BLEND;
                    printf(IKT_TAG "BLEND   %d frames -> back to animation\\r\\n",
                           TEST_IK_RELEASE_BLEND);
                }
                else
                {
                    state = IK_IDLE;
                    printf(IKT_TAG "IDLE    animation resumed (instant)\\r\\n");
                }
            }
        }

        /* ---- 松开后的混合：从触点插值回动画目标 ---- */
        if (state == IK_BLEND)
        {
            float w = 1.0f - (float)(blend_k + 1) / (float)TEST_IK_RELEASE_BLEND;

            if (w < 0.0f)
            {
                w = 0.0f;
            }

            spine_instance_set_ik_target(in, ik_name,
                                         rel_wx * w + anim_wx * (1.0f - w),
                                         rel_wy * w + anim_wy * (1.0f - w));

            blend_k++;

            if (blend_k >= TEST_IK_RELEASE_BLEND)
            {
                spine_instance_clear_ik(in);        /* 混合结束：交回动画 */
                state = IK_IDLE;
                printf(IKT_TAG "IDLE    animation resumed\\r\\n");
            }
        }
'''


def main():
    s = io.open(P, encoding="utf-8").read()

    if "blend_k" in s:
        print("already patched")
        return

    start = s.find("        /* ---- 触摸：屏幕坐标 -> 骨架世界坐标 ---- */")
    end = s.find("        {\n            uint32_t now = plat_now_ms();")

    assert start > 0, "touch block not found"
    assert end > start, "update block not found"

    s = s[:start] + NEW_BLOCK + "\n" + s[end:]

    # 状态变量
    s = s.replace("""    int touched = 0;
    int last_x = 0;
    int last_y = 0;""",
"""    int touched = 0;            /* 是否收到过触摸（用于 RESULT） */
    int last_x = 0;
    int last_y = 0;
    int state = IK_IDLE;
    int blend_k = 0;
    uint32_t last_press_ms = 0;
    float rel_wx = 0.0f, rel_wy = 0.0f;     /* 松开瞬间的覆盖点 */
    float anim_wx = 0.0f, anim_wy = 0.0f;   /* 松开瞬间的动画目标 */""")

    # 状态行加状态字段
    s = s.replace('''                printf(IKT_TAG "%s t=%lus %.1ffps tip=(%.0f,%.0f) %s\\r\\n",
                       ik_name, (unsigned long)((plat_now_ms() - t0) / 1000u),
                       (double)((float)f / ((float)(plat_now_ms() - t0) / 1000.0f)),
                       (double)tipx, (double)tipy,
                       (touched != 0) ? "touched" : "waiting");''',
'''                printf(IKT_TAG "%s t=%lus %.1ffps state=%s tip=(%.0f,%.0f)\\r\\n",
                       ik_name, (unsigned long)((plat_now_ms() - t0) / 1000u),
                       (double)((float)f / ((float)(plat_now_ms() - t0) / 1000.0f)),
                       (state == IK_ACTIVE) ? "ACTIVE" : ((state == IK_BLEND) ? "BLEND" : "IDLE"),
                       (double)tipx, (double)tipy);''')

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("state machine installed")


if __name__ == "__main__":
    main()
