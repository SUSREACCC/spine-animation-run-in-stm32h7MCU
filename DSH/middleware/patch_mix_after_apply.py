#!/usr/bin/env python3
"""Make set_ik_mix authoritative by applying it AFTER AnimationState::apply().

Diagnosis on hardware: the status line showed

    mix=0.00/1.00      (our pose value / the value the solver reads)

The `aim` animation has an IK-mix timeline that writes aim-ik's mix to 1 on
every `AnimationState::apply()`, so any value we write from application code is
overwritten before the constraint runs. That is why the fade never worked and
the touch felt like an instant jump.

Fix: store the requested mix in the instance and write it inside
apply_ik_overrides(), which already runs between apply() and
updateWorldTransform() - the same authoritative slot used for the IK target.

Run from the project root:  python DSH/middleware/patch_mix_after_apply.py
"""
import io

CPP = "User/spine_api.cpp"

OLD_STRUCT = """    /* IK 目标覆盖（运行时驱动用） */
    spine_ik_slot_t ik[SPINE_IK_MAX];                          /* RGBA8888 */"""
NEW_STRUCT = """    /* IK 目标覆盖（运行时驱动用） */
    spine_ik_slot_t ik[SPINE_IK_MAX];                          /* RGBA8888 */

    /* IK 混入覆盖：必须在 AnimationState::apply() 之后写入才不会被动画覆盖 */
    struct { spine::IkConstraint *ik; float mix; } mix[SPINE_IK_MAX];"""

OLD_SET = """    /* 同时写未约束 pose 与 applied pose：不同版本里 IkConstraint::update()
     * 读的是 *_appliedPose，直接写两边最保险。 */
    ik->getPose().setMix(mix);
    ik->getAppliedPose().setMix(mix);

    return 1;
}"""

NEW_SET = """    /* 不能直接写：动画的 IK mix 时间轴会在每帧 apply() 时覆盖它。
     * 存起来，交给 apply_ik_overrides() 在 apply() 之后写。 */
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if ((in->mix[i].ik == ik) || (in->mix[i].ik == nullptr))
        {
            in->mix[i].ik = ik;
            in->mix[i].mix = mix;

            /* 立刻也写一遍，保证不含 update 的路径（如 get 读回）一致 */
            ik->getPose().setMix(mix);

            return 1;
        }
    }

    return 0;                       /* 槽满了 */
}"""

OLD_GET = """    return (ik == nullptr) ? 0.0f : ik->getPose().getMix();"""

NEW_GET = """    if (ik == nullptr)
    {
        return 0.0f;
    }

    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->mix[i].ik == ik)
        {
            return in->mix[i].mix;
        }
    }

    return ik->getPose().getMix();"""

OLD_APPLY = """    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->ik[i].ik == nullptr)
        {
            continue;
        }

        spine::Bone &target = in->ik[i].ik->getTarget();"""

NEW_APPLY = """    /* 先写 IK 混入（动画的 mix 时间轴刚在 apply() 里写过，这里夺回控制权） */
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->mix[i].ik != nullptr)
        {
            in->mix[i].ik->getPose().setMix(in->mix[i].mix);
            in->mix[i].ik->getAppliedPose().setMix(in->mix[i].mix);
        }
    }

    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->ik[i].ik == nullptr)
        {
            continue;
        }

        spine::Bone &target = in->ik[i].ik->getTarget();"""


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "in->mix[i].ik" in s:
        print("already patched")
        return

    for old, new, what in ((OLD_STRUCT, NEW_STRUCT, "struct"),
                           (OLD_SET, NEW_SET, "set_ik_mix"),
                           (OLD_GET, NEW_GET, "ik_mix"),
                           (OLD_APPLY, NEW_APPLY, "apply_ik_overrides")):
        assert old in s, what + " pattern not found"
        s = s.replace(old, new, 1)
        print("patched:", what)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)


if __name__ == "__main__":
    main()
