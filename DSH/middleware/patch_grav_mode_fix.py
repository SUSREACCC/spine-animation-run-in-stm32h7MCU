#!/usr/bin/env python3
"""Repair the accidental edit in spine_play and apply the "no animation" mode to
spine_gravity_test only.

A previous patch used str.replace() which hit the FIRST occurrence (spine_play)
instead of the gravity demo.  This script reverts that region and re-applies the
change after the gravity function's header.

Run from the project root:  python DSH/middleware/patch_grav_mode_fix.py
"""
import io

PATH = "User/spine_test.cpp"
CRLF = chr(92) + "r" + chr(92) + "n"          # literal \r\n for C string

OLD_SET = '    state.setAnimation(0, spine::String(anim), true);'

NEW_SET = "\n".join([
    '    const bool has_anim = (anim != nullptr) && (anim[0] != 0);',
    '',
    '    if (has_anim)',
    '    {',
    '        state.setAnimation(0, spine::String(anim), true);',
    '    }',
    '    else',
    '    {',
    '        printf("[GRAV] no animation: static pose, gravity is the only motion' + CRLF + '");',
    '    }',
])

OLD_UPD = "\n".join([
    '        state.update(dt);',
    '        state.apply(skeleton);',
    '        skeleton.updateWorldTransform(spine::Physics_Update);',
])

NEW_UPD = "\n".join([
    '        if (has_anim)',
    '        {',
    '            state.update(dt);',
    '            state.apply(skeleton);',
    '        }',
    '',
    '        skeleton.updateWorldTransform(spine::Physics_Update);',
])


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "spine_play_duo" not in s:
        raise SystemExit("split marker missing")

    head, rest = s.split('extern "C" uint8_t spine_play_duo', 1)

    # ---- 1) 修复 spine_play 里的误伤 ----
    lines = head.split("\n")
    out = []
    i = 0
    fixed_set = 0
    fixed_upd = 0

    while i < len(lines):
        ln = lines[i]

        if ln.strip() == "if (has_anim)" and not fixed_set:
            # 跳过整个误插入的块，直到 printf 的结束行
            j = i
            while j < len(lines) and "gravity is the only motion" not in lines[j]:
                j += 1
            # printf 字符串被真实换行拆成两行，跳到收尾的 ");"
            j += 1
            while j < len(lines) and lines[j].strip() != ");" and lines[j].strip() != "}":
                j += 1
            # 跳过剩余的花括号
            while j < len(lines) and lines[j].strip() in ("}", ""):
                if lines[j].strip() == "}":
                    j += 1
                    break
                j += 1
            out.append(OLD_SET)
            fixed_set += 1
            i = j
            continue

        if ln.strip() == "if (has_anim)" and fixed_set and not fixed_upd:
            # 更新块：if (has_anim) { update; apply; } / blank / updateWorldTransform
            while i < len(lines) and lines[i].strip() != "}":
                i += 1
            i += 1                                   # 跳过 }
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            if i < len(lines) and "updateWorldTransform" in lines[i]:
                out.extend(OLD_UPD.split("\n"))
                fixed_upd += 1
                i += 1
                continue

        out.append(ln)
        i += 1

    head = "\n".join(out)

    # ---- 2) 只在 gravity 函数里应用新逻辑 ----
    g_start = rest.find('extern "C" uint8_t spine_gravity_test')
    if g_start < 0:
        raise SystemExit("gravity function not found")

    before = rest[:g_start]
    grav = rest[g_start:]
    head_of_grav = grav.find("{")

    body = grav[head_of_grav:]
    if "has_anim" not in body:
        body = body.replace(OLD_SET, NEW_SET, 1)
        body = body.replace(OLD_UPD, NEW_UPD, 1)
    grav = grav[:head_of_grav] + body

    io.open(PATH, "w", encoding="utf-8", newline="").write(head + 'extern "C" uint8_t spine_play_duo' + before + grav)
    print("reverted spine_play:", fixed_set, fixed_upd, "| gravity mode applied")


if __name__ == "__main__":
    main()
