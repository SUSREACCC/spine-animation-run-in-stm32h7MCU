#!/usr/bin/env python3
"""Add spine_instance_release_ik_keep_pose().

Two ways to drop the IK target override:

  clear_ik()                  - restores the target bone's pose, THEN clears the
                                slots.  Use when the interaction ends for good.
  release_ik_keep_pose()      - drops the override but LEAVES the bone where it
                                is, so a following animation mix can blend from
                                that pose.  Use for the "switch back to the walk
                                animation with a transition" workflow.

Why the second one exists: clear_ik() snaps the target bone back to the value
captured before the first override, which is exactly the twitch you see if you
then start an animation transition.  With keep_pose the animation's own timeline
for that bone takes over and its mix does the smoothing.

Caveat (documented in the header): if the normal animation does NOT animate the
target bone, the target simply stays where the finger left it - the leg will keep
leaning toward the old point.  The workflow relies on the "normal" clip driving
that bone.

Run from the project root:  python DSH/middleware/patch_release_ik.py
"""
import io

H = "User/spine_api.h"
CPP = "User/spine_api.cpp"

H_ADD = r'''
/**
 * 丢弃 IK 目标覆盖，但**保留目标骨骼当前姿态**（不还原）。
 *
 * 用途：配合"两段动画 + 过渡"的复位方案 ——
 *   按下 play(交互动画, 腿无时间轴) + set_ik_mix(1.0) + 每帧 set_ik_target
 *   松开 play(正常动画, mix) + release_ik_keep_pose()
 * 这样正常动画里目标骨骼的 timeline 会从"手指最后的位置"平滑过渡回正常目标，
 * 不需要运行时代码做插值。
 *
 * 与 spine_instance_clear_ik() 的区别：
 *   clear_ik()            还原目标骨骼到首次覆盖前的姿态（交互彻底结束时用）
 *   release_ik_keep_pose() 不还原，留给动画混合接管
 *
 * 注意：如果正常动画**不驱动**目标骨骼，目标会停在手指最后的位置，
 *       腿会一直偏向那里（这时应该用 clear_ik()）。
 */
void spine_instance_release_ik_keep_pose(spine_instance_t *in);
'''

CPP_ADD = r'''
void spine_instance_release_ik_keep_pose(spine_instance_t *in)
{
    if (in == nullptr)
    {
        return;
    }

    /* 只清覆盖表，不动骨骼姿态 */
    memset(in->ik, 0, sizeof(in->ik));
}
'''


def main():
    h = io.open(H, encoding="utf-8").read()

    if "spine_instance_release_ik_keep_pose" in h:
        print("header: already patched")
    else:
        anchor = "void spine_instance_clear_ik(spine_instance_t *in);"
        assert anchor in h, "clear_ik declaration not found"
        h = h.replace(anchor, H_ADD.strip() + "\n\n" + anchor, 1)
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: release_ik_keep_pose declared")

    s = io.open(CPP, encoding="utf-8").read()

    if "spine_instance_release_ik_keep_pose" in s:
        print("cpp: already patched")
        return

    anchor = "void spine_instance_clear_ik(spine_instance_t *in)"
    assert anchor in s, "clear_ik implementation not found"
    s = s.replace(anchor, CPP_ADD.strip() + "\n\n" + anchor, 1)
    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("cpp: release_ik_keep_pose implemented")


if __name__ == "__main__":
    main()
