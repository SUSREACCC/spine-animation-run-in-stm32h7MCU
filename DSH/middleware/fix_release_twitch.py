#!/usr/bin/env python3
"""Fix the release twitch (both test modules).

Root cause of the visible double-snap:
    release frame:
        clear_ik()            -> the limb snaps back to the animated pose
        update()              -> one un-overridden update
        get_ik_target()       -> read the animation target
        ... and the SAME frame still draws, from the animated pose
    next frame:
        blend starts by setting the target back to the touch point -> snaps again

Fix:
  1. after capturing the animation target, immediately re-apply the override at
     the touch point and SKIP the rest of that frame (no draw) -> one dropped
     frame (~16 ms), no visible snap;
  2. replace the fixed 8-frame linear blend with exponential smoothing
     (time constant TEST_IK_RELEASE_TAU_MS), ending when the residual is small
     enough that clear_ik() cannot be seen.

Run from the project root:  python DSH/middleware/fix_release_twitch.py
"""
import io

TAU_DEF = """
/* 松手回复的时间常数（毫秒）：越小回得越快 */
#ifndef TEST_IK_RELEASE_TAU_MS
#define TEST_IK_RELEASE_TAU_MS  120
#endif
"""


def patch_interactive():
    p = "User/spine_ik_interactive.c"
    s = io.open(p, encoding="utf-8").read()

    if "TEST_IK_RELEASE_TAU_MS" in s:
        print("interactive: already patched")
        return

    # 1) 时间常数宏
    s = s.replace("#ifndef IK_TOUCH_TIMEOUT_MS", TAU_DEF.strip() + "\n\n#ifndef IK_TOUCH_TIMEOUT_MS", 1)

    # 2) 状态变量
    s = s.replace("    int blend_k = 0;", "    int blend_k = 0;\n    float blend_t = 0.0f;", 1)

    # 3) 松手：捕获后立刻恢复覆盖，并跳过本帧
    old = """                spine_instance_clear_ik(in);
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
                }"""
    new = """                spine_instance_clear_ik(in);
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
                    printf(IKT_TAG "BLEND   tau=%dms -> back to animation\\r\\n",
                           TEST_IK_RELEASE_TAU_MS);
                    continue;                   /* 丢掉这一帧，避免双跳变 */
                }

                state = IK_IDLE;
                printf(IKT_TAG "IDLE    animation resumed (instant)\\r\\n");
                continue;"""
    assert old in s, "interactive release block not found"
    s = s.replace(old, new, 1)

    # 4) 混合：指数平滑
    old_blend = """        /* ---- 松开后的混合：从触点插值回动画目标 ---- */
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
        }"""
    new_blend = """        /* ---- 松开后的混合：指数平滑逼近动画目标 ---- */
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
                    printf(IKT_TAG "IDLE    animation resumed (%d frames)\\r\\n", blend_k);
                }
            }
        }"""
    assert old_blend in s, "interactive blend block not found"
    s = s.replace(old_blend, new_blend, 1)

    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("interactive: release fixed (skip frame + exponential smoothing)")


def patch_seq():
    p = "User/spine_anim_seq.c"
    s = io.open(p, encoding="utf-8").read()

    if "TEST_IK_RELEASE_TAU_MS" in s:
        print("seq: already patched")
        return

    s = s.replace('#define SEQ_MIX_SECONDS', TAU_DEF.strip() + "\n\n#define SEQ_MIX_SECONDS", 1)

    # ctx 里加时间累加
    s = s.replace("    int      blend_k;", "    int      blend_k;\n    float    blend_t;", 1)
    s = s.replace("    c->blend_k = 0;", "    c->blend_k = 0;\n    c->blend_t = 0.0f;", 1)

    old = """                    spine_instance_clear_ik(in);
                    spine_instance_update(in, 1.0f / 60.0f);
                    spine_instance_get_ik_target(in, ph->ik, &ik.anim_wx, &ik.anim_wy);

                    ik.blend_k = 0;
                    ik.state = SEQ_IK_BLEND;
                    printf(SEQ_TAG "  release -> blend back\\r\\n");"""
    new = """                    spine_instance_clear_ik(in);
                    spine_instance_update(in, 1.0f / 60.0f);
                    spine_instance_get_ik_target(in, ph->ik, &ik.anim_wx, &ik.anim_wy);

                    /* 立刻恢复覆盖，并跳过本帧渲染，避免"回原位再跳回"的双跳变 */
                    spine_instance_set_ik_target(in, ph->ik, ik.rel_wx, ik.rel_wy);

                    ik.blend_k = 0;
                    ik.blend_t = 0.0f;
                    ik.state = SEQ_IK_BLEND;
                    printf(SEQ_TAG "  release -> blend back (tau=%dms)" SEQ_NL,
                           TEST_IK_RELEASE_TAU_MS);
                    continue;"""
    assert old in s, "seq release block not found"
    s = s.replace(old, new, 1)

    old_blend = """                if (ik.state == SEQ_IK_BLEND)
                {
                    float w = 1.0f - (float)(ik.blend_k + 1) / (float)SEQ_RELEASE_BLEND;

                    if (w < 0.0f)
                    {
                        w = 0.0f;
                    }

                    spine_instance_set_ik_target(in, ph->ik,
                                                 ik.rel_wx * w + ik.anim_wx * (1.0f - w),
                                                 ik.rel_wy * w + ik.anim_wy * (1.0f - w));

                    if (++ik.blend_k >= SEQ_RELEASE_BLEND)
                    {
                        spine_instance_clear_ik(in);
                        ik.state = SEQ_IK_IDLE;
                    }
                }"""
    new_blend = """                if (ik.state == SEQ_IK_BLEND)
                {
                    float a = 1.0f - expf(-dt * 1000.0f / (float)TEST_IK_RELEASE_TAU_MS);

                    ik.rel_wx += (ik.anim_wx - ik.rel_wx) * a;
                    ik.rel_wy += (ik.anim_wy - ik.rel_wy) * a;

                    spine_instance_set_ik_target(in, ph->ik, ik.rel_wx, ik.rel_wy);

                    ik.blend_t += dt;
                    ik.blend_k++;

                    {
                        float dx = ik.anim_wx - ik.rel_wx;
                        float dy = ik.anim_wy - ik.rel_wy;

                        if ((sqrtf(dx * dx + dy * dy) < 2.0f) || (ik.blend_t > 0.6f))
                        {
                            spine_instance_clear_ik(in);
                            ik.state = SEQ_IK_IDLE;
                        }
                    }
                }"""
    assert old_blend in s, "seq blend block not found"
    s = s.replace(old_blend, new_blend, 1)

    io.open(p, "w", encoding="utf-8", newline="").write(s)
    print("seq: release fixed (skip frame + exponential smoothing)")


if __name__ == "__main__":
    patch_interactive()
    patch_seq()
