#!/usr/bin/env python3
"""Aim phase: "extra touch action" style IK (mix fade, no target interpolation).

The user's design: the touch IK is an EXTRA action that normally does not
participate (mix = 0).  On touch we raise its mix and drive the target; on
release we fade the mix back to 0 and the limb returns to the animation pose.

This is different from the leg case (spine_ik_interactive.c), where the IK is
already in use by the walk animation, so the release there keeps mix = 1 and
blends the TARGET instead.

State machine:
    IDLE --press--> FADE_IN --mix=1--> ACTIVE --release--> FADE_OUT --mix=0--> IDLE

Run from the project root:  python DSH/middleware/patch_aim_extra_action.py
"""
import io

P = "User/spine_anim_seq.c"

NEW_CTX = '''/*----------------------------------------------------------------- 触摸 -> IK（额外动作） */

/* aim-ik 平时 mix=0：只有触摸时把 mix 升起来，松手再降回去。
 * 与"接管现有 IK"（spine_ik_interactive.c 里腿那种）不同：
 * 这里不插值目标，只淡入淡出约束强度，部位自然回到动画姿态。 */
enum { SEQ_IK_IDLE = 0, SEQ_IK_FADE_IN, SEQ_IK_ACTIVE, SEQ_IK_FADE_OUT };

#ifndef SEQ_IK_FADE_IN_MS
#define SEQ_IK_FADE_IN_MS       100     /* 按下时 mix 0 -> 1 用时 */
#endif

#ifndef SEQ_IK_FADE_OUT_MS
#define SEQ_IK_FADE_OUT_MS      220     /* 松手时 mix 1 -> 0 用时 */
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
'''

NEW_BLOCK = '''            /* ---- 该段的触摸 -> IK（mix 淡入淡出） ---- */
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
            }
'''


def main():
    s = io.open(P, encoding="utf-8").read()

    if "SEQ_IK_FADE_OUT_MS" in s:
        print("already patched")
        return

    # 1) 替换 ctx 定义
    start = s.find("/*----------------------------------------------------------------- 触摸 -> IK 覆盖 */")
    end = s.find("/* 把屏幕坐标换算成骨架世界坐标 */")
    assert start > 0 and end > start, "ctx block not found"
    s = s[:start] + NEW_CTX.strip() + "\n\n" + s[end:]

    # 2) 替换触摸处理块（到"spine_instance_update(in, dt);"之前）
    bstart = s.find("            /* ---- 该段的触摸 -> IK ---- */")
    bend = s.find("            spine_instance_update(in, dt);", bstart)
    assert bstart > 0 and bend > bstart, "touch block not found"
    s = s[:bstart] + NEW_BLOCK.strip() + "\n\n" + s[bend:]

    # 3) 阶段开始时不再直接把 mix 设成 1
    s = s.replace("""            spine_instance_set_ik_mix(in, ph->ik, 1.0f);    /* 该约束默认 mix=0 */
            seq_ik_reset(&ik);

            printf(SEQ_TAG "  %s mix -> %.2f (设置后立即读回)" SEQ_NL,
                   ph->ik, (double)spine_instance_ik_mix(in, ph->ik));""",
"""            spine_instance_set_ik_mix(in, ph->ik, 0.0f);    /* 平时不参与 */
            seq_ik_reset(&ik);

            printf(SEQ_TAG "  %s 平时 mix=0，触摸时淡入" SEQ_NL, ph->ik);""")

    # 4) 每秒状态行里的 ikstate 换成 mix/状态
    s = s.replace('''                    printf(SEQ_TAG "  t=%ds  anim=%s  mix=%.2f  ikstate=%d  gt=0x%02X" SEQ_NL,
                           (int)((now - t_start) / 1000u),
                           (cur != 0) ? cur : "?",
                           (double)spine_instance_ik_mix(in, ph->ik),
                           ik.state,
                           (unsigned)spine_touch_status());''',
'''                    printf(SEQ_TAG "  t=%ds  anim=%s  mix=%.2f  st=%d  gt=0x%02X" SEQ_NL,
                           (int)((now - t_start) / 1000u),
                           (cur != 0) ? cur : "?",
                           (double)ik.mix,
                           ik.state,
                           (unsigned)spine_touch_status());''')

    # 5) 阶段结束时清理
    s = s.replace("""            spine_instance_clear_ik(in);            /* 还原目标骨骼 */
            spine_instance_set_ik_mix(in, ph->ik, 0.0f);""",
"""            spine_instance_set_ik_mix(in, ph->ik, 0.0f);
            spine_instance_clear_ik(in);            /* 还原目标骨骼 */""")

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("aim phase: mix fade in/out (extra-touch-action style)")


if __name__ == "__main__":
    main()
