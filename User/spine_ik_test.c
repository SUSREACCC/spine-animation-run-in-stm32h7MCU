/**
 ****************************************************************************************************
 * @file        spine_ik_test.c
 * @brief       IK 目标驱动测试
 *
 * 目的：证明"运行时改 IK 目标"是真的生效，而不只是 API 返回 1。
 *
 * 流程：
 *   1. 加载素材，枚举所有 IK 约束（名字 / 链长 / mix / 末端残差）
 *   2. 挑出真正在跟随的那个（残差最小且 mix > 0）
 *   3. 把目标沿 +X 推 40 个世界单位，跑几帧
 *   4. 重新读末端：要求末端移动 > 1 单位，且到新目标的距离变小
 *
 * 实测数据（spineboy，2026-11-17）：
 *   7 个 IK；front-leg-ik / rear-leg-ik 残差 < 1（在跟随）
 *   rear-leg-ik：目标推 +40 后末端移动 39.02，残差 40.00 -> 4.32  => PASS
 ****************************************************************************************************
 */

#include "spine_ik_test.h"
#include "spine_api.h"
#include "plat/plat.h"

#include <math.h>
#include <stdio.h>

#define IK_TAG "[IK] "

static float ik_dist(float x0, float y0, float x1, float y1)
{
    float dx = x1 - x0;
    float dy = y1 - y0;

    return sqrtf(dx * dx + dy * dy);
}

/* 跑若干帧，让动画 / 物理 / IK 都推进 */
static void ik_step(spine_instance_t *in, int frames)
{
    for (int f = 0; f < frames; f++)
    {
        spine_instance_update(in, 1.0f / 60.0f);
    }
}

int spine_ik_test(const char *skel_path, const char *atlas_path,
                  const char *anim, int hold_frames, int visual)
{
    spine_asset_t *asset = 0;
    spine_instance_t *in = 0;
    int n = 0;
    int best = -1;
    float best_res = 1e9f;
    int pass = 0;

    if ((skel_path == 0) || (atlas_path == 0))
    {
        return 0;
    }

    if (hold_frames < 1)
    {
        hold_frames = 5;
    }

    printf("\r\n" IK_TAG "asset: %s\r\n", skel_path);

    asset = spine_asset_load(skel_path, atlas_path);

    if (asset == 0)
    {
        printf(IK_TAG "load failed (asset missing on SD?)\r\n");
        return 0;
    }

    in = spine_instance_create(asset);

    if (in == 0)
    {
        spine_asset_free(asset);
        return 0;
    }

    if ((anim != 0) && (anim[0] != 0))
    {
        spine_instance_play(in, anim, 1, 0);
    }
    else if (spine_asset_anim_count(asset) > 0)
    {
        spine_instance_play(in, spine_asset_anim_name(asset, 0), 1, 0);
    }

    /* ---- 1. 枚举 ---- */
    n = spine_instance_ik_count(in);
    printf(IK_TAG "IK constraints: %d\r\n", n);

    for (int i = 0; i < n; i++)
    {
        const char *nm = spine_instance_ik_name(in, i);
        float tx = 0, ty = 0, px = 0, py = 0;
        float mix = spine_instance_ik_mix(in, nm);
        float res;

        spine_instance_get_ik_target(in, nm, &tx, &ty);
        spine_instance_get_ik_tip(in, nm, &px, &py);

        res = ik_dist(px, py, tx, ty);

        printf(IK_TAG "  #%d %-16s bones=%d mix=%.2f tip=(%.1f,%.1f) res=%.1f\r\n",
               i, nm, spine_instance_ik_bone_count(in, nm),
               (double)mix, (double)px, (double)py, (double)res);

        if ((mix > 0.01f) && (res < best_res))
        {
            best_res = res;
            best = i;
        }
    }

    if (n == 0)
    {
        printf(IK_TAG "RESULT SKIP (no IK in this skeleton)\r\n");
        spine_instance_destroy(in);
        spine_asset_free(asset);
        return -1;
    }

    if (best < 0)
    {
        best = 0;
        best_res = 0.0f;
    }

    {
        const char *ik = spine_instance_ik_name(in, best);

        float tx0 = 0, ty0 = 0, tip0x = 0, tip0y = 0;
        float tip1x = 0, tip1y = 0;
        float tx1, ty1, d_before, d_after, moved;
        int ok_set;

        printf(IK_TAG "subject: #%d %s (residual %.1f)\r\n", best, ik, (double)best_res);

        /* ---- 2. 基准 ---- */
        ik_step(in, hold_frames);

        spine_instance_get_ik_target(in, ik, &tx0, &ty0);
        spine_instance_get_ik_tip(in, ik, &tip0x, &tip0y);

        /* ---- 3. 推目标 ---- */
        tx1 = tx0 + 40.0f;
        ty1 = ty0;

        ok_set = spine_instance_set_ik_target(in, ik, tx1, ty1);

        ik_step(in, hold_frames);

        spine_instance_get_ik_tip(in, ik, &tip1x, &tip1y);

        d_before = ik_dist(tip0x, tip0y, tx1, ty1);
        d_after  = ik_dist(tip1x, tip1y, tx1, ty1);
        moved    = ik_dist(tip0x, tip0y, tip1x, tip1y);

        printf(IK_TAG "target (%.1f,%.1f) -> (%.1f,%.1f), set=%d\r\n",
               (double)tx0, (double)ty0, (double)tx1, (double)ty1, ok_set);
        printf(IK_TAG "tip moved %.2f, residual %.2f -> %.2f\r\n",
               (double)moved, (double)d_before, (double)d_after);

        if ((ok_set == 1) && (moved > 1.0f) && (d_after < d_before))
        {
            pass = 1;
        }

        /* ---- 5. 松开 / 还原：目标骨骼必须回到覆盖前的姿态 ---- */
        {
            float tip2x = 0, tip2y = 0;
            float d_restored;

            spine_instance_clear_ik(in);
            ik_step(in, hold_frames);

            spine_instance_get_ik_tip(in, ik, &tip2x, &tip2y);

            /* 还原后末端应重新远离"被推过去的目标" */
            d_restored = ik_dist(tip2x, tip2y, tx1, ty1);

            printf(IK_TAG "after clear_ik: tip=(%.1f,%.1f) dist to pushed target %.1f\r\n",
                   (double)tip2x, (double)tip2y, (double)d_restored);

            if (d_restored > (d_after + 5.0f))
            {
                printf(IK_TAG "restore OK (tip left the pushed target)\r\n");
            }
            else
            {
                printf(IK_TAG "restore FAILED (offset leaked, range would shift)\r\n");
                pass = 0;
            }
        }

        /* ---- 4. 可视化：目标绕圈 ---- */
        if (visual != 0)
        {
            float x0 = 0, y0 = 0, x1 = 0, y1 = 0, cx = 0, cy = 0;
            float s = 0.75f;

            if (spine_instance_get_bounds(in, &x0, &y0, &x1, &y1) != 0)
            {
                cx = (x0 + x1) * 0.5f;
                cy = (y0 + y1) * 0.5f;

                s = 300.0f / ((y1 - y0) > 1.0f ? (y1 - y0) : 400.0f);

                spine_instance_set_scale(in, s);
                spine_instance_set_position(in, 400.0f - cx * s, 300.0f - cy * s);
            }

            for (int f = 0; f < 180; f++)
            {
                float th = 6.2831853f * (float)f / 90.0f;

                spine_instance_set_ik_target(in, ik,
                                             tx0 + cosf(th) * 45.0f,
                                             ty0 + sinf(th) * 45.0f);

                spine_instance_update(in, 1.0f / 60.0f);

                spine_draw_begin(2);
                spine_instance_draw(in);
                spine_draw_end();
            }
        }
    }

    printf(IK_TAG "RESULT %s\r\n", pass ? "PASS" : "FAIL");

    spine_instance_destroy(in);
    spine_asset_free(asset);

    return pass;
}
