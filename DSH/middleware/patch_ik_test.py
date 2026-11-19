#!/usr/bin/env python3
"""Add spine_ik_test() to spine_test.cpp and wire it into selftest.

The test proves IK target driving really works, not just that the API returns 1:

  1. loads the asset and lists every IK constraint (name + chain length)
  2. records the chain tip (last bone's end) with the animation's own target
  3. moves the IK target to a new world position for a few frames
  4. re-reads the tip and checks that it MOVED TOWARD the new target and that
     the residual distance shrank

It also renders a few seconds with the target circling so the effect is visible.

Run from the project root:  python DSH/middleware/patch_ik_test.py
"""
import io

CPP = "User/spine_test.cpp"
SELFTEST = "User/selftest.c"

TEST = r'''
/*----------------------------------------------------------------- IK 约束测试 */

#include "spine_api.h"
#include "plat/plat.h"

static float ik_len(float x0, float y0, float x1, float y1)
{
    float dx = x1 - x0;
    float dy = y1 - y0;

    return sqrtf(dx * dx + dy * dy);
}

int spine_ik_test(const char *skel_path, const char *atlas_path)
{
    printf("" "\r\n[IK] asset: %s\r\n" "", skel_path);

    spine_asset_t *asset = spine_asset_load(skel_path, atlas_path);

    if (asset == 0)
    {
        printf("" "[IK] load failed (asset missing on SD?)\r\n" "");
        return 0;
    }

    spine_instance_t *in = spine_instance_create(asset);

    if (in == 0)
    {
        spine_asset_free(asset);
        return 0;
    }

    /* 有动画就先播一个，让骨骼处在自然姿态 */
    if (spine_asset_anim_count(asset) > 0)
    {
        spine_instance_play(in, spine_asset_anim_name(asset, 0), 1, 0);
    }

    int n = spine_instance_ik_count(in);

    printf("" "[IK] IK constraints: %d\r\n" "", n);

    for (int i = 0; i < n; i++)
    {
        const char *nm = spine_instance_ik_name(in, i);
        float tx = 0, ty = 0, px = 0, py = 0;

        spine_instance_get_ik_target(in, nm, &tx, &ty);
        spine_instance_get_ik_tip(in, nm, &px, &py);

        printf("" "[IK]   #%d %s  bones=%d  target=(%.1f,%.1f) tip=(%.1f,%.1f)\r\n" "",
               i, nm, spine_instance_ik_bone_count(in, nm),
               (double)tx, (double)ty, (double)px, (double)py);
    }

    if (n == 0)
    {
        printf("" "[IK] RESULT SKIP (no IK constraint in this skeleton)\r\n" "");
        spine_instance_destroy(in);
        spine_asset_free(asset);
        return 1;
    }

    const char *ik = spine_instance_ik_name(in, 0);
    int pass = 0;

    /* --- 基准：用动画自身的姿态跑几帧 --- */
    for (int f = 0; f < 5; f++)
    {
        spine_instance_update(in, 1.0f / 60.0f);
    }

    float tx0 = 0, ty0 = 0, tip0x = 0, tip0y = 0;

    spine_instance_get_ik_target(in, ik, &tx0, &ty0);
    spine_instance_get_ik_tip(in, ik, &tip0x, &tip0y);

    /* --- 把目标往 +X 方向推 40 个世界单位 --- */
    float tx1 = tx0 + 40.0f;
    float ty1 = ty0;

    int ok_set = spine_instance_set_ik_target(in, ik, tx1, ty1);

    for (int f = 0; f < 5; f++)
    {
        spine_instance_update(in, 1.0f / 60.0f);
    }

    float tip1x = 0, tip1y = 0;

    spine_instance_get_ik_tip(in, ik, &tip1x, &tip1y);

    float d_before = ik_len(tip0x, tip0y, tx1, ty1);      /* 旧末端到新目标 */
    float d_after  = ik_len(tip1x, tip1y, tx1, ty1);      /* 新末端到新目标 */
    float moved    = ik_len(tip0x, tip0y, tip1x, tip1y);  /* 末端实际位移 */

    printf("" "[IK] set=%d  target (%.1f,%.1f)->(%.1f,%.1f)\r\n" "",
           ok_set, (double)tx0, (double)ty0, (double)tx1, (double)ty1);
    printf("" "[IK] tip moved %.2f units, dist to target %.2f -> %.2f\r\n" "",
           (double)moved, (double)d_before, (double)d_after);

    if ((ok_set == 1) && (moved > 1.0f) && (d_after < d_before))
    {
        pass = 1;
    }

    /* --- 可视化：目标绕圈，腿应该跟着动 --- */
    {
        float s = 300.0f / 400.0f;
        float cx = 0, cy = 0, x0 = 0, y0 = 0, x1 = 0, y1 = 0;

        spine_instance_get_bounds(in, &x0, &y0, &x1, &y1);
        cx = (x0 + x1) * 0.5f;
        cy = (y0 + y1) * 0.5f;

        spine_instance_set_scale(in, s);
        spine_instance_set_position(in, 400.0f - cx * s, 280.0f - cy * s);

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

    printf("" "[IK] RESULT %s\r\n" "", pass ? ""PASS"" : ""FAIL""");

    spine_instance_destroy(in);
    spine_asset_free(asset);

    return pass;
}
'''


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "spine_ik_test" in s:
        print("test already present")
    else:
        idx = s.find("/*--------------------------------------------------------------- 世界重力")
        if idx < 0:
            idx = len(s)
        s = s[:idx] + TEST.strip() + "\n\n" + s[idx:]

        if "#include <math.h>" not in s:
            s = s.replace('#include "spine_api.h"', '#include "spine_api.h"\n\n#include <math.h>', 1)

        io.open(CPP, "w", encoding="utf-8", newline="").write(s)
        print("spine_test.cpp: spine_ik_test added")

    # 头文件声明
    hd = "User/spine_test.h"
    h = io.open(hd, encoding="utf-8").read()

    if "spine_ik_test" not in h:
        h = h.replace("#ifdef __cplusplus\nextern \"C\" {\n#endif",
"""#ifdef __cplusplus
extern "C" {
#endif

/** IK 目标驱动测试：枚举约束、驱动目标、校验末端跟随。返回 1 = PASS */
int spine_ik_test(const char *skel_path, const char *atlas_path);""", 1)
        io.open(hd, "w", encoding="utf-8", newline="").write(h)
        print("spine_test.h: declaration added")

    # selftest 调用（在 api_demo 之后、demo 之前）
    st = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_ik_test" not in st:
        st = st.replace("    api_demo();",
"""    api_demo();

    /* IK 目标驱动测试（spineboy 素材，TF 卡） */
    (void)spine_ik_test("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas");""", 1)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(st)
        print("selftest.c: IK test wired")


if __name__ == "__main__":
    main()
