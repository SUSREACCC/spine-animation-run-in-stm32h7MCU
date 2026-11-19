#!/usr/bin/env python3
"""IK API round 2: expose mix, and make spine_ik_test pick an IK that really tracks.

Round 1 findings on the spineboy asset (real device log):

    [IK] IK constraints: 7
      #0 board-ik        bones=1  target=(-131.8,-69.0)  tip=(-329.7,-69.5)
      #1 front-leg-ik    bones=2  target=(-42.0,-29.1)   tip=(-41.9,-29.6)   <-- tracks
      #2 rear-leg-ik     bones=2  target=(28.0,-37.8)    tip=(28.0,-37.8)    <-- tracks
      #3 front-foot-ik   bones=1  target=(-13.5,-0.0)    tip=(-13.7,-0.2)
      #4 rear-foot-ik    bones=1  target=(61.9,-0.5)     tip=(62.1,-0.2)
      #5 aim-torso-ik    bones=1  target=(302.4,-569.7)  tip=(18.9,-271.9)
      #6 aim-ik          bones=1  target=(302.4,-569.7)  tip=(16.1,-299.1)

board-ik was a bad test subject: a 1-bone IK whose target is far outside reach, and
the tip did not move.  front/rear-leg-ik are 2-bone IK with tip == target, i.e. they
are actively solving.

Changes:
  * new API: spine_instance_ik_mix() / spine_instance_set_ik_mix()
  * the test prints mix + |tip-target| for every IK and runs the move test on the
    IK with the smallest residual (the one that is actually tracking)

Run from the project root:  python DSH/middleware/patch_ik_mix.py
"""
import io

H = "User/spine_api.h"
CPP = "User/spine_api.cpp"
TEST = "User/spine_test.cpp"

H_ADD = r'''
/** 读取 IK 混入（0..1） */
float spine_instance_ik_mix(spine_instance_t *in, const char *ik_name);

/** 设置 IK 混入（0 = 关闭该约束，1 = 全量）。返回 1 = 成功 */
int spine_instance_set_ik_mix(spine_instance_t *in, const char *ik_name, float mix);
'''

CPP_ADD = r'''
float spine_instance_ik_mix(spine_instance_t *in, const char *ik_name)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    return (ik == nullptr) ? 0.0f : ik->getPose().getMix();
}

int spine_instance_set_ik_mix(spine_instance_t *in, const char *ik_name, float mix)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if (ik == nullptr)
    {
        return 0;
    }

    if (mix < 0.0f) { mix = 0.0f; }
    if (mix > 1.0f) { mix = 1.0f; }

    ik->getPose().setMix(mix);

    return 1;
}
'''


def add_api():
    h = io.open(H, encoding="utf-8").read()
    if "spine_instance_ik_mix" not in h:
        h = h.replace("/** 清掉所有待应用的 IK 目标覆盖（恢复由动画/setup 驱动的目标） */",
                      H_ADD.strip() + "\n\n/** 清掉所有待应用的 IK 目标覆盖（恢复由动画/setup 驱动的目标） */")
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: mix API added")

    s = io.open(CPP, encoding="utf-8").read()
    if "spine_instance_ik_mix" not in s:
        anchor = "void spine_instance_clear_ik(spine_instance_t *in)"
        s = s.replace(anchor, CPP_ADD.strip() + "\n\n" + anchor, 1)
        io.open(CPP, "w", encoding="utf-8", newline="").write(s)
        print("cpp: mix API added")


NEW_BLOCK = r'''    /* 逐个打印：mix 和 tip 到目标的残差，挑出真正在跟随的那个 */
    int best = -1;
    float best_d = 1e9f;

    for (int i = 0; i < n; i++)
    {
        const char *nm = spine_instance_ik_name(in, i);
        float tx = 0, ty = 0, px = 0, py = 0;

        spine_instance_get_ik_target(in, nm, &tx, &ty);
        spine_instance_get_ik_tip(in, nm, &px, &py);

        float d = ik_len(px, py, tx, ty);

        printf("[IK]   #%d %-16s bones=%d mix=%.2f tip=(%.1f,%.1f) residual=%.1f\r\n",
               i, nm, spine_instance_ik_bone_count(in, nm),
               (double)spine_instance_ik_mix(in, nm),
               (double)px, (double)py, (double)d);

        if ((d < best_d) && (spine_instance_ik_mix(in, nm) > 0.01f))
        {
            best_d = d;
            best = i;
        }
    }

    if (best < 0)
    {
        best = 0;
    }

    printf("[IK] test subject: #%d %s (residual %.1f)\r\n",
           best, spine_instance_ik_name(in, best), (double)best_d);'''

OLD_BLOCK_START = "    for (int i = 0; i < n; i++)\n    {\n        const char *nm = spine_instance_ik_name(in, i);\n        float tx = 0, ty = 0, px = 0, py = 0;\n\n        spine_instance_get_ik_target(in, nm, &tx, &ty);\n        spine_instance_get_ik_tip(in, nm, &px, &py);\n\n        printf(\"[IK]   #%d %s  bones=%d  target=(%.1f,%.1f) tip=(%.1f,%.1f)\\r\\n\",\n               i, nm, spine_instance_ik_bone_count(in, nm),\n               (double)tx, (double)ty, (double)px, (double)py);\n    }"


def patch_test():
    s = io.open(TEST, encoding="utf-8").read()

    if "test subject:" in s:
        print("test already improved")
        return

    assert OLD_BLOCK_START in s, "old listing block not found"
    s = s.replace(OLD_BLOCK_START, NEW_BLOCK, 1)

    s = s.replace('    const char *ik = spine_instance_ik_name(in, 0);',
                  '    const char *ik = spine_instance_ik_name(in, best);', 1)

    io.open(TEST, "w", encoding="utf-8", newline="").write(s)
    print("test: picks the tracking IK, prints mix + residual")


if __name__ == "__main__":
    add_api()
    patch_test()
