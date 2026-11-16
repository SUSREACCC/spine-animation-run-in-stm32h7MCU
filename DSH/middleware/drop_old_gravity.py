#!/usr/bin/env python3
"""Remove the old world-gravity registry from the test harness (it is now owned by
spine_api.cpp and keyed by instances, not skeletons) and adapt the demo call sites.

    spine_test.cpp:  delete  #define GRAV_REG_MAX ... spine_gravity_registry_count
                     keep    spine_set_gravity(skel, gx, gy)  and spine_dump_bones
    call sites:      spine_register/unregister_skeleton(x)  -> removed
                     spine_world_set_gravity(gx, gy)        -> spine_set_gravity(&skeleton, gx, gy)

Run from the project root:  python DSH/middleware/drop_old_gravity.py
"""
import io

PATH = "User/spine_test.cpp"


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")

    # ---- 1) 删除旧的注册表实现 ----
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("#define GRAV_REG_MAX"):
            start = i
            break

    if start is not None:
        end = None
        for j in range(start, len(lines)):
            if lines[j].startswith("extern \"C\" int spine_gravity_registry_count"):
                end = j
                break
        if end is None:
            raise SystemExit("registry end not found")
        del lines[start:end + 1]
        print("removed old gravity registry lines %d..%d" % (start + 1, end + 1))
    else:
        print("old registry already removed")

    s = "\n".join(lines)

    # ---- 2) 调用点适配 ----
    s = s.replace("        spine_register_skeleton(skA);            /* 加入世界重力注册表 */\n", "")
    s = s.replace("        spine_register_skeleton(skB);\n", "")
    s = s.replace("        spine_unregister_skeleton(skA);\n", "")
    s = s.replace("        spine_unregister_skeleton(skB);\n", "")
    s = s.replace("    spine_register_skeleton(&skeleton);          /* 注册到世界重力 */\n\n", "")
    s = s.replace("        spine_world_set_gravity(cosf(theta), sinf(theta));   /* 世界级：所有注册骨架一起变 */",
                  "        spine_set_gravity(&skeleton, cosf(theta), sinf(theta));")
    s = s.replace('printf("[GRAV] physics constraints in skeleton: %d\\r\\n",\n           (int)skeleton.getPhysicsConstraints().size());',
                  'printf("[GRAV] physics constraints in skeleton: %d\\r\\n",\n           (int)skeleton.getPhysicsConstraints().size());')

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("call sites adapted")


if __name__ == "__main__":
    main()
