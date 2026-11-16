#!/usr/bin/env python3
"""Add a world-level gravity layer on top of the per-skeleton one.

Current state: gravity lives on each Skeleton instance (Skeleton::_gravityX/Y),
so spine_set_gravity(skel, gx, gy) only affects ONE animation object.  The C
header, however, declared a dangling spine_set_gravity_dir(gx, gy) that was never
implemented - misleading.

New API (two layers):

    /* 单个对象级 */
    void spine_set_gravity(spine::Skeleton *skel, float gx, float gy);

    /* 世界级：保存全局值，并立即同步到所有已注册骨架 */
    void spine_world_set_gravity(float gx, float gy);
    void spine_register_skeleton(void *skel);      /* 注册时自动套用当前世界重力 */
    void spine_unregister_skeleton(void *skel);

A skeleton created after a world gravity change picks it up at registration.

Run from the project root:  python DSH/middleware/patch_world_gravity.py
"""
import io

PATH = "User/spine_test.cpp"
HEADER = "User/spine_test.h"

IMPL = r'''
/*----------------------------------------------------------------- 世界级重力 */

#define GRAV_REG_MAX 32

static spine::Skeleton *g_grav_reg[GRAV_REG_MAX];
static int              g_grav_reg_count = 0;
static float            g_world_gx = 0.0f;
static float            g_world_gy = 1.0f;

extern "C" void spine_set_gravity(spine::Skeleton *skel, float gx, float gy)
{
    if (skel != nullptr)
    {
        skel->setGravityX(gx);
        skel->setGravityY(gy);
    }
}

/** 世界重力：保存并立即同步到所有已注册骨架。 */
extern "C" void spine_world_set_gravity(float gx, float gy)
{
    g_world_gx = gx;
    g_world_gy = gy;

    for (int i = 0; i < g_grav_reg_count; i++)
    {
        spine::Skeleton *sk = g_grav_reg[i];

        if (sk != nullptr)
        {
            sk->setGravityX(gx);
            sk->setGravityY(gy);
        }
    }
}

extern "C" float spine_world_get_gravity_x(void) { return g_world_gx; }
extern "C" float spine_world_get_gravity_y(void) { return g_world_gy; }

/** 注册骨架：立刻套用当前世界重力，之后世界重力变化会自动同步。 */
extern "C" void spine_register_skeleton(void *skel)
{
    spine::Skeleton *sk = (spine::Skeleton *)skel;

    if (sk == nullptr)
    {
        return;
    }

    for (int i = 0; i < g_grav_reg_count; i++)
    {
        if (g_grav_reg[i] == sk)
        {
            return;                     /* 已注册 */
        }
    }

    if (g_grav_reg_count >= GRAV_REG_MAX)
    {
        printf("[GRAV] registry full (%d)\r\n", GRAV_REG_MAX);
        return;
    }

    sk->setGravityX(g_world_gx);
    sk->setGravityY(g_world_gy);
    g_grav_reg[g_grav_reg_count++] = sk;
}

extern "C" void spine_unregister_skeleton(void *skel)
{
    spine::Skeleton *sk = (spine::Skeleton *)skel;

    for (int i = 0; i < g_grav_reg_count; i++)
    {
        if (g_grav_reg[i] == sk)
        {
            for (int j = i; j < (g_grav_reg_count - 1); j++)
            {
                g_grav_reg[j] = g_grav_reg[j + 1];
            }
            g_grav_reg_count--;
            g_grav_reg[g_grav_reg_count] = nullptr;
            return;
        }
    }
}

extern "C" int spine_gravity_registry_count(void) { return g_grav_reg_count; }
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "spine_world_set_gravity" in s:
        print("world gravity already present")
        return

    # 用新的实现替换旧的单对象实现块
    old_start = s.find("/*----------------------------------------------------------------- 重力方向 + 物理形变 */")
    old_end = s.find("extern \"C\" void spine_dump_bones")
    if old_start < 0 or old_end < 0:
        raise SystemExit("old gravity block not found")

    s = s[:old_start] + IMPL.strip() + "\n\n" + s[old_end:]

    # 演示里改用世界级接口，并注册骨架
    s = s.replace("    spine::Bone *probe_bone = skeleton.findBone(spine::String(target->getName().buffer()));",
                  "    spine_register_skeleton(&skeleton);          /* 注册到世界重力 */\n\n"
                  "    spine::Bone *probe_bone = skeleton.findBone(spine::String(target->getName().buffer()));", 1)

    s = s.replace("        spine_set_gravity(&skeleton, cosf(theta), sinf(theta));",
                  "        spine_world_set_gravity(cosf(theta), sinf(theta));   /* 世界级：所有注册骨架一起变 */", 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)

    # 头文件：删掉悬空声明，换成世界级接口
    h = io.open(HEADER, encoding="utf-8").read()
    h = h.replace("/* 设置当前骨架的全局重力方向（作用于所有物理约束） */\n"
                  "void spine_set_gravity_dir(float gx, float gy);\n",
                  "/* ---------------------------------------------------------------\n"
                  " * 重力：两层 API\n"
                  " *   单个对象：C++ 里调用 spine_set_gravity(skel, gx, gy)\n"
                  " *   世界级  ：spine_world_set_gravity(gx, gy) 会同步到所有已注册骨架\n"
                  " * 方向遵循 spine 约定：y 轴向下，(0,1)=向下，(0,-1)=向上\n"
                  " * --------------------------------------------------------------- */\n"
                  "void  spine_world_set_gravity(float gx, float gy);\n"
                  "float spine_world_get_gravity_x(void);\n"
                  "float spine_world_get_gravity_y(void);\n"
                  "void  spine_register_skeleton(void *skel);\n"
                  "void  spine_unregister_skeleton(void *skel);\n"
                  "int   spine_gravity_registry_count(void);\n")
    io.open(HEADER, "w", encoding="utf-8", newline="").write(h)
    print("world gravity implemented and wired")


if __name__ == "__main__":
    main()
