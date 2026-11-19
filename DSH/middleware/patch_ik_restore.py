#!/usr/bin/env python3
"""Fix the IK target offset leak.

Symptom reported on hardware: touch, release, and the leg keeps oscillating in
a SHIFTED range (0..20 deg became 40..60 deg) instead of returning to the
animation. Cause: the override writes into the target bone's applied pose, and
`spine_instance_clear_ik()` only emptied the slot table - the bone kept the last
written local x/y. spineboy's IK target bones are not animated, so nothing ever
wrote them back -> permanent constant offset.

Fix: capture the target bone's local pose the first time a slot is used, and
restore it in clear_ik() before zeroing the table. Then the animation owns the
bone again and the motion range is restored exactly.

Run from the project root:  python DSH/middleware/patch_ik_restore.py
"""
import io

CPP = "User/spine_api.cpp"
H = "User/spine_api.h"

OLD_T = "typedef struct { spine::IkConstraint *ik; float wx, wy; } spine_ik_slot_t;"
NEW_T = """typedef struct
{
    spine::IkConstraint *ik;
    float wx, wy;              /* 覆盖目标（世界坐标） */
    float base_lx, base_ly;    /* 首次覆盖前目标骨骼的局部姿态 */
    int   captured;
} spine_ik_slot_t;"""

OLD_SET = """    slot->ik = ik;
    slot->wx = world_x;
    slot->wy = world_y;

    return 1;"""

NEW_SET = """    if ((slot->captured == 0) || (slot->ik != ik))
    {
        /* 记住覆盖前的目标骨骼姿态，clear 时原样还回去 */
        spine::BonePose &base = ik->getTarget().getAppliedPose();

        slot->base_lx = base.getX();
        slot->base_ly = base.getY();
        slot->captured = 1;
    }

    slot->ik = ik;
    slot->wx = world_x;
    slot->wy = world_y;

    return 1;"""

OLD_CLEAR = """void spine_instance_clear_ik(spine_instance_t *in)
{
    if (in != nullptr)
    {
        memset(in->ik, 0, sizeof(in->ik));
    }
}"""

NEW_CLEAR = """void spine_instance_clear_ik(spine_instance_t *in)
{
    if (in == nullptr)
    {
        return;
    }

    /* 关键：把目标骨骼的姿态还原，否则动画不驱动这根骨骼时，
     * 偏移量会永久留在骨架上（表现为运动范围整体平移）。 */
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if ((in->ik[i].ik != nullptr) && (in->ik[i].captured != 0))
        {
            spine::BonePose &p = in->ik[i].ik->getTarget().getAppliedPose();

            p.setX(in->ik[i].base_lx);
            p.setY(in->ik[i].base_ly);
        }
    }

    memset(in->ik, 0, sizeof(in->ik));
}"""


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "base_lx" in s:
        print("already patched")
        return

    assert OLD_T in s, "slot typedef not found"
    s = s.replace(OLD_T, NEW_T, 1)

    assert OLD_SET in s, "set_ik_target tail not found"
    s = s.replace(OLD_SET, NEW_SET, 1)

    assert OLD_CLEAR in s, "clear_ik not found"
    s = s.replace(OLD_CLEAR, NEW_CLEAR, 1)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("cpp: capture baseline + restore in clear_ik")

    # 头文件语义说明
    h = io.open(H, encoding="utf-8").read()

    if "还原到覆盖前的姿态" not in h:
        h = h.replace("/** 清掉所有待应用的 IK 目标覆盖（恢复由动画/setup 驱动的目标） */",
                      "/** 清掉所有待应用的 IK 目标覆盖，并把目标骨骼还原到覆盖前的姿态\n *  （否则动画不驱动该骨骼时，偏移会永久保留，表现为运动范围整体平移） */")
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: clear_ik semantics documented")


if __name__ == "__main__":
    main()
