#!/usr/bin/env python3
"""Interactive IK test: play 'walk', log the IK tip so it can be verified from
the serial log alone (no framebuffer dump needed)."""
import io

P = "User/spine_ik_interactive.c"
BS = "\\"


def main():
    s = io.open(P, encoding="utf-8").read()

    if "tip=(%.1f,%.1f)" in s:
        print("already patched")
        return

    # 1) 指定 walk
    old_anim = """    if (spine_asset_anim_count(asset) > 0)
    {
        spine_instance_play(in, spine_asset_anim_name(asset, 0), 1, 0);
    }"""
    new_anim = """    /* 用 walk：有实际运动，才能从串口或画面看出更新 */
    {
        int played = 0;
        int cnt = spine_asset_anim_count(asset);

        for (int i = 0; i < cnt; i++)
        {
            const char *nm = spine_asset_anim_name(asset, i);

            if ((nm != 0) && (nm[0] == 'w') && (nm[1] == 'a') && (nm[2] == 'l'))
            {
                spine_instance_play(in, nm, 1, 0);
                played = 1;
                break;
            }
        }

        if ((played == 0) && (cnt > 0))
        {
            spine_instance_play(in, spine_asset_anim_name(asset, 0), 1, 0);
        }
    }"""
    assert old_anim in s
    s = s.replace(old_anim, new_anim, 1)

    # 2) 状态行带末端坐标
    old_print = s[s.find('            printf(IKT_TAG "%s  t=%lus  %s'):]
    old_end = old_print.find(";")
    old_block = old_print[:old_end + 1]

    new_block = (
        "            {\n"
        "                float tipx = 0, tipy = 0;\n"
        "\n"
        "                spine_instance_get_ik_tip(in, ik_name, &tipx, &tipy);\n"
        "\n"
        '                printf(IKT_TAG "%s t=%lus tip=(%.1f,%.1f) %s' + BS + "r" + BS + 'n",\n'
        "                       ik_name, (unsigned long)((plat_now_ms() - t0) / 1000u),\n"
        "                       (double)tipx, (double)tipy,\n"
        '                       (touched != 0) ? "touched" : "waiting");\n'
        "            }"
    )

    s = s.replace(old_block, new_block, 1)
    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("patched: walk animation + tip logging")


if __name__ == "__main__":
    main()
