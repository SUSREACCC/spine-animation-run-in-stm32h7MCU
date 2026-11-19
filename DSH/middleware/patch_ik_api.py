#!/usr/bin/env python3
"""Add a normalized IK API to spine_api.

What the runtime allows (verified in spine-cpp 4.3 sources):
  * Skeleton::findConstraint<IkConstraint>(name)             -- by name
  * IkConstraint::getTarget() -> Bone&                       -- target bone
  * IkConstraint::getBones() -> Array<BonePose*>             -- 1 or 2 constrained bones
      (these are _constrainedPose sub-objects: resolve Bone* via IkConstraintData::getBones()[i]->getIndex())
  * IkConstraint::update() reads target->_appliedPose->_worldX/Y, so writing the target
    bone's applied pose BEFORE updateWorldTransform(Physics_Update) takes effect the same frame.

Added API (C, no C++ types leak out):

    int         spine_instance_ik_count(spine_instance_t *in);
    const char *spine_instance_ik_name(spine_instance_t *in, int index);
    int         spine_instance_ik_bone_count(spine_instance_t *in, const char *ik_name);

    int  spine_instance_set_ik_target(spine_instance_t *in, const char *ik_name,
                                      float world_x, float world_y);
    int  spine_instance_get_ik_target(spine_instance_t *in, const char *ik_name,
                                      float *world_x, float *world_y);
    int  spine_instance_get_ik_tip(spine_instance_t *in, const char *ik_name,
                                   float *world_x, float *world_y);
    void spine_instance_clear_ik(spine_instance_t *in);

Coordinates are skeleton world space (spine units), not screen pixels.

Run from the project root:  python DSH/middleware/patch_ik_api.py
"""
import io

H = "User/spine_api.h"
CPP = "User/spine_api.cpp"

H_ADD = r'''
/*==================================================================================================
 * IK 约束（运行时驱动）
 *
 * 坐标一律是**骨架世界坐标**（spine 单位），不是屏幕像素。
 * 目标在下一帧的 update() 里生效（会先跑动画 apply，再写目标，最后解算 IK）。
 *=================================================================================================*/

/** IK 约束数量 */
int spine_instance_ik_count(spine_instance_t *in);

/** 第 index 个 IK 约束的名字（找不到返回 NULL） */
const char *spine_instance_ik_name(spine_instance_t *in, int index);

/** 该 IK 链有几根骨骼（通常 1 或 2） */
int spine_instance_ik_bone_count(spine_instance_t *in, const char *ik_name);

/** 设置 IK 目标位置（骨架世界坐标）。返回 1 = 成功 */
int spine_instance_set_ik_target(spine_instance_t *in, const char *ik_name,
                                 float world_x, float world_y);

/** 读取 IK 目标当前的世界坐标。返回 1 = 成功 */
int spine_instance_get_ik_target(spine_instance_t *in, const char *ik_name,
                                 float *world_x, float *world_y);

/** 读取 IK 链末端的实际世界坐标（用于判定 IK 是否真的跟随）。返回 1 = 成功 */
int spine_instance_get_ik_tip(spine_instance_t *in, const char *ik_name,
                              float *world_x, float *world_y);

/** 清掉所有待应用的 IK 目标覆盖（恢复由动画/setup 驱动的目标） */
void spine_instance_clear_ik(spine_instance_t *in);
'''

CPP_ADD = r'''
/*----------------------------------------------------------------- IK 约束 */

int spine_instance_ik_count(spine_instance_t *in)
{
    if ((in == nullptr) || (in->skel == nullptr))
    {
        return 0;
    }

    spine::Array<spine::Constraint *> &cs = in->skel->getConstraints();
    int n = 0;

    for (size_t i = 0; i < cs.size(); i++)
    {
        if (cs[i]->getRTTI().instanceOf(spine::IkConstraint::rtti))
        {
            n++;
        }
    }

    return n;
}

static spine::IkConstraint *ik_at(spine_instance_t *in, int index)
{
    if ((in == nullptr) || (in->skel == nullptr) || (index < 0))
    {
        return nullptr;
    }

    spine::Array<spine::Constraint *> &cs = in->skel->getConstraints();
    int n = 0;

    for (size_t i = 0; i < cs.size(); i++)
    {
        if (cs[i]->getRTTI().instanceOf(spine::IkConstraint::rtti))
        {
            if (n == index)
            {
                return (spine::IkConstraint *)cs[i];
            }
            n++;
        }
    }

    return nullptr;
}

const char *spine_instance_ik_name(spine_instance_t *in, int index)
{
    spine::IkConstraint *ik = ik_at(in, index);

    return (ik == nullptr) ? nullptr : ik->getData().getName().buffer();
}

static spine::IkConstraint *ik_by_name(spine_instance_t *in, const char *name)
{
    if ((in == nullptr) || (in->skel == nullptr) || (name == nullptr) || (name[0] == 0))
    {
        return nullptr;
    }

    return in->skel->findConstraint<spine::IkConstraint>(spine::String(name));
}

int spine_instance_ik_bone_count(spine_instance_t *in, const char *ik_name)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    return (ik == nullptr) ? 0 : (int)ik->getBones().size();
}

int spine_instance_set_ik_target(spine_instance_t *in, const char *ik_name,
                                 float world_x, float world_y)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if ((ik == nullptr) || (world_x != world_x) || (world_y != world_y))
    {
        return 0;                   /* 找不到，或传了 NaN */
    }

    ik_override_t *slot = nullptr;

    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->ik[i].ik == ik)
        {
            slot = &in->ik[i];
            break;
        }

        if ((slot == nullptr) && (in->ik[i].ik == nullptr))
        {
            slot = &in->ik[i];
        }
    }

    if (slot == nullptr)
    {
        return 0;                   /* 覆盖槽满了 */
    }

    slot->ik = ik;
    slot->wx = world_x;
    slot->wy = world_y;

    return 1;
}

int spine_instance_get_ik_target(spine_instance_t *in, const char *ik_name,
                                 float *world_x, float *world_y)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if (ik == nullptr)
    {
        return 0;
    }

    spine::BonePose *p = &ik->getTarget().getAppliedPose();

    if (world_x != nullptr) { *world_x = p->getWorldX(); }
    if (world_y != nullptr) { *world_y = p->getWorldY(); }

    return 1;
}

int spine_instance_get_ik_tip(spine_instance_t *in, const char *ik_name,
                              float *world_x, float *world_y)
{
    spine::IkConstraint *ik = ik_by_name(in, ik_name);

    if ((ik == nullptr) || (ik->getBones().size() == 0))
    {
        return 0;
    }

    /* getBones() 返回的是 _constrainedPose 子对象，必须经 BoneData 索引换回 Bone */
    spine::IkConstraintData &d = (spine::IkConstraintData &)ik->getData();
    spine::Array<spine::BoneData *> &bds = d.getBones();

    if (bds.size() == 0)
    {
        return 0;
    }

    spine::BoneData *last = bds[bds.size() - 1];
    spine::Bone &bone = *in->skel->getBones()[last->getIndex()];

    float tx = 0.0f, ty = 0.0f;

    bone.getAppliedPose().localToWorld(bone.getData().getLength(), 0.0f, tx, ty);

    if (world_x != nullptr) { *world_x = tx; }
    if (world_y != nullptr) { *world_y = ty; }

    return 1;
}

void spine_instance_clear_ik(spine_instance_t *in)
{
    if (in != nullptr)
    {
        memset(in->ik, 0, sizeof(in->ik));
    }
}

/* 在动画 apply 之后、updateWorldTransform 之前把 IK 目标写进目标骨骼 */
static void apply_ik_overrides(spine_instance_t *in)
{
    for (int i = 0; i < SPINE_IK_MAX; i++)
    {
        if (in->ik[i].ik == nullptr)
        {
            continue;
        }

        spine::Bone &target = in->ik[i].ik->getTarget();

        float lx = 0.0f, ly = 0.0f;

        target.getAppliedPose().worldToParent(in->ik[i].wx, in->ik[i].wy, lx, ly);

        spine::BonePose &p = target.getAppliedPose();

        p.setX(lx);
        p.setY(ly);
    }
}
'''


def main():
    h = io.open(H, encoding="utf-8").read()

    if "spine_instance_set_ik_target" not in h:
        anchor = "/** 已注册实例数（诊断用；实例创建时自动注册，销毁时自动注销） */"
        h = h.replace(anchor, H_ADD.strip() + "\n\n" + anchor)
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: IK API added")

    s = io.open(CPP, encoding="utf-8").read()

    if "spine_instance_set_ik_target" in s:
        print("cpp: already patched")
        return

    # 1) 实例结构里加覆盖槽
    s = s.replace("""    uint32_t tint;""",
"""    uint32_t tint;

    /* IK 目标覆盖（运行时驱动用） */
    struct ik_slot { spine::IkConstraint *ik; float wx, wy; } ik[SPINE_IK_MAX];""", 1)

    # 2) 常量
    s = s.replace("#define SPINE_MAX_INST", "#define SPINE_IK_MAX        4\n#define SPINE_MAX_INST", 1)

    # 3) 实现块插到"世界重力"之前
    anchor = "/*----------------------------------------------------------------- 世界重力 */"
    assert anchor in s
    s = s.replace(anchor, CPP_ADD.strip() + "\n\n" + anchor, 1)

    # 4) update 里应用覆盖
    s = s.replace("""    in->state->update(dt);
    in->state->apply(*in->skel);

    /* 推进骨架时间：物理约束的步进量来自 _time 的增量 */""",
"""    in->state->update(dt);
    in->state->apply(*in->skel);

    /* IK 目标覆盖：必须在 apply 之后写入，否则会被动画轨道覆盖 */
    apply_ik_overrides(in);

    /* 推进骨架时间：物理约束的步进量来自 _time 的增量 */""", 1)

    # 5) destroy 时清空
    s = s.replace("""    in->skel = nullptr;""",
"""    memset(in->ik, 0, sizeof(in->ik));
    in->skel = nullptr;""", 1)

    # 6) 需要的头文件
    if "spine/IkConstraint.h" not in s:
        s = s.replace('#include "spine/Skeleton.h"',
                      '#include "spine/Skeleton.h"\n#include "spine/IkConstraint.h"\n#include "spine/Bone.h"', 1)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("cpp: IK API implemented and wired into update()")


if __name__ == "__main__":
    main()
