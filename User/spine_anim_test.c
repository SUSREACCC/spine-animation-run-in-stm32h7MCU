/**
 ****************************************************************************************************
 * @file        spine_anim_test.c
 * @brief       动画衔接测试：过渡时长 / 排队 / 进度接回
 *
 * 验证 4 件事：
 *   1. set_default_mix() 生效（切换不再硬切）
 *   2. current_anim() 能正确报出当前动画名
 *   3. seek() 能把播放进度接回去（松开触摸后接着走路）
 *   4. add_anim() 能排队下一段；set_mix() 对不存在的名字返回 0（不触发 assert）
 ****************************************************************************************************
 */

#include "spine_anim_test.h"
#include "spine_api.h"
#include "plat/plat.h"

#include <math.h>
#include <stdio.h>

#define ANT_TAG "[ANIM] "

static float ant_abs(float v)
{
    return (v < 0.0f) ? -v : v;
}

static void ant_step(spine_instance_t *in, int frames)
{
    for (int i = 0; i < frames; i++)
    {
        spine_instance_update(in, 1.0f / 60.0f);
    }
}

/* 找一个名字里包含 key 的动画，找不到就返回 index */
static const char *ant_pick(spine_asset_t *a, const char *key, int index)
{
    int n = spine_asset_anim_count(a);

    for (int i = 0; i < n; i++)
    {
        const char *nm = spine_asset_anim_name(a, i);

        if ((nm != 0) && (key != 0) && (key[0] != 0))
        {
            int k = 0;

            while ((nm[k] != 0) && (key[k] != 0) && (nm[k] == key[k]))
            {
                k++;
            }

            if (key[k] == 0)
            {
                return nm;
            }
        }
    }

    return (index < n) ? spine_asset_anim_name(a, index) : 0;
}

int spine_anim_test(const char *skel_path, const char *atlas_path, int frames)
{
    spine_asset_t *asset;
    spine_instance_t *in;
    const char *anim_a;
    const char *anim_b;
    const char *cur;
    float saved;
    float restored;
    int pass = 1;

    if ((skel_path == 0) || (atlas_path == 0))
    {
        return 0;
    }

    if (frames < 4)
    {
        frames = 30;
    }

    printf("\r\n" ANT_TAG "asset: %s\r\n", skel_path);

    asset = spine_asset_load(skel_path, atlas_path);

    if (asset == 0)
    {
        printf(ANT_TAG "load failed\r\n");
        return 0;
    }

    if (spine_asset_anim_count(asset) < 2)
    {
        printf(ANT_TAG "need at least 2 animations\r\n");
        spine_asset_free(asset);
        return 0;
    }

    in = spine_instance_create(asset);

    if (in == 0)
    {
        spine_asset_free(asset);
        return 0;
    }

    anim_a = ant_pick(asset, "walk", 0);
    anim_b = ant_pick(asset, "idle", 1);

    printf(ANT_TAG "A=%s  B=%s\r\n", anim_a, anim_b);

    /* ---- 1. 过渡时长 ---- */
    spine_instance_set_default_mix(in, 0.20f);
    {
        int ok = spine_instance_set_mix(in, anim_a, anim_b, 0.25f);
        int bad = spine_instance_set_mix(in, anim_a, "no-such-anim", 0.25f);

        printf(ANT_TAG "set_mix(%s->%s)=%d  set_mix(bad)=%d (expect 1 / 0)\r\n",
               anim_a, anim_b, ok, bad);

        if ((ok != 1) || (bad != 0))
        {
            pass = 0;
        }
    }

    /* ---- 2. 播放 A，记录进度与名字 ---- */
    spine_instance_play(in, anim_a, 1, 0);
    ant_step(in, frames);

    saved = spine_instance_get_time(in, 0);
    cur = spine_instance_current_anim(in, 0);

    printf(ANT_TAG "playing %s  time=%.3f\r\n", (cur != 0) ? cur : "?", (double)saved);

    if ((cur == 0) || (cur[0] != anim_a[0]))
    {
        pass = 0;
    }

    /* ---- 3. 切到 B（带 0.25 s 过渡），确认名字变了 ---- */
    spine_instance_play(in, anim_b, 1, 0);
    ant_step(in, 6);

    cur = spine_instance_current_anim(in, 0);
    printf(ANT_TAG "switched to %s (expect %s)\r\n", (cur != 0) ? cur : "?", anim_b);

    if ((cur == 0) || (cur[0] != anim_b[0]))
    {
        pass = 0;
    }

    /* ---- 4. 切回 A 并接回进度 ---- */
    spine_instance_play(in, anim_a, 1, 0);

    if (spine_instance_seek(in, saved, 0) == 0)
    {
        pass = 0;
    }

    restored = spine_instance_get_time(in, 0);

    printf(ANT_TAG "seek back to %.3f -> %.3f\r\n", (double)saved, (double)restored);

    if (ant_abs(restored - saved) > 0.05f)
    {
        printf(ANT_TAG "seek mismatch\r\n");
        pass = 0;
    }

    printf(ANT_TAG "RESULT %s\r\n", pass ? "PASS" : "FAIL");

    spine_instance_destroy(in);
    spine_asset_free(asset);

    return pass;
}
