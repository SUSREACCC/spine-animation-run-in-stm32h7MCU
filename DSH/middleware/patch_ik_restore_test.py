#!/usr/bin/env python3
"""Add a release-restore regression check to spine_ik_test.

After the "push the target" phase, release the override and let the animation
run: the chain tip must move BACK away from the pushed target. If the old bug
(the target bone kept the written pose) came back, the tip would stay pinned
near the pushed point, so this check fails loudly.

Run from the project root:  python DSH/middleware/patch_ik_restore_test.py
"""
import io

P = "User/spine_ik_test.c"

OLD = """        if ((ok_set == 1) && (moved > 1.0f) && (d_after < d_before))
        {
            pass = 1;
        }
"""

NEW = """        if ((ok_set == 1) && (moved > 1.0f) && (d_after < d_before))
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

            printf(IK_TAG "after clear_ik: tip=(%.1f,%.1f) dist to pushed target %.1f\\r\\n",
                   (double)tip2x, (double)tip2y, (double)d_restored);

            if (d_restored > (d_after + 5.0f))
            {
                printf(IK_TAG "restore OK (tip left the pushed target)\\r\\n");
            }
            else
            {
                printf(IK_TAG "restore FAILED (offset leaked, range would shift)\\r\\n");
                pass = 0;
            }
        }
"""


def main():
    s = io.open(P, encoding="utf-8").read()

    if "restore OK" in s:
        print("already patched")
        return

    assert OLD in s, "pass-check block not found"
    s = s.replace(OLD, NEW, 1)

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("spine_ik_test: release-restore check added")


if __name__ == "__main__":
    main()
