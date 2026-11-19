#!/usr/bin/env python3
"""Split the self-test into macro-controlled sections.

* removes the old inline spine_ik_test (moved to User/spine_ik_test.c)
* guards every test call in selftest_run() with its TEST_xxx switch
* adds User/spine_ik_test.c to the uvprojx
* default config (test_cfg.h) runs only IK (+ optional demo)

Run from the project root:  python DSH/middleware/split_tests.py
"""
import io
import re

SELFTEST = "User/selftest.c"
SPINE_TEST = "User/spine_test.cpp"
PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"


def strip_old_ik_test():
    s = io.open(SPINE_TEST, encoding="utf-8").read()

    start = s.find("/*----------------------------------------------------------------- IK 约束测试 */")
    if start < 0:
        print("spine_test.cpp: no inline IK test (ok)")
        return

    # 找到该测试函数的结尾：下一个章节注释之前
    end = s.find("/*--------------------------------------------------------------- 世界重力", start)
    if end < 0:
        end = len(s)

    s = s[:start] + s[end:]
    io.open(SPINE_TEST, "w", encoding="utf-8", newline="").write(s)
    print("spine_test.cpp: inline IK test removed")


def patch_selftest():
    s = io.open(SELFTEST, encoding="utf-8").read()

    # 1) 引入开关头
    if "test_cfg.h" not in s:
        s = s.replace('#include "selftest.h"', '#include "selftest.h"\n#include "test_cfg.h"\n#include "spine_ik_test.h"', 1)

    # 2) 逐个测试加宏开关
    guards = [
        ("    (void)sdram_test();", "TEST_DRIVERS"),
        ("    (void)lcd_test();", "TEST_DRIVERS"),
        ("    (void)qspi_test();", "TEST_DRIVERS"),
        ("    (void)sd_test();", "TEST_DRIVERS"),
        ("    (void)fatfs_test();", "TEST_DRIVERS"),
        ("    fb_bench();", "TEST_FBBENCH"),
    ]

    for call, macro in guards:
        if call in s and ("#if " + macro) not in s.split(call)[0][-80:]:
            s = s.replace(call, "#if %s\n%s\n#endif" % (macro, call), 1)

    # 3) Spine 旧项目整块
    block_start = s.find('    (void)spine_anim_sheet(')
    block_end = s.find('    api_demo();')

    if (block_start > 0) and (block_end > block_start):
        block = s[block_start:block_end]
        if "#if TEST_SHEET" not in s[block_start - 40:block_start]:
            guarded = "#if TEST_SHEET\n" + block[:block.find('(void)spine_gravity_test')] + "#endif\n\n"
            guarded += "#if TEST_GRAVITY\n" + block[block.find('(void)spine_gravity_test'):block.find('(void)spine_play_duo')] + "#endif\n\n"
            guarded += "#if TEST_DUO\n" + block[block.find('(void)spine_play_duo'):] + "#endif\n\n"
            s = s[:block_start] + guarded + s[block_end:]

    # 4) api_demo
    if "#if TEST_API_DEMO" not in s:
        s = s.replace("    api_demo();", "#if TEST_API_DEMO\n    api_demo();\n#endif", 1)

    # 5) IK 测试改为独立模块
    old_ik = re.search(r"    \(void\)spine_ik_test\([^;]*\);", s)
    if old_ik:
        s = s[:old_ik.start()] + """#if TEST_IK
    /* IK 目标驱动：spineboy 素材，TF 卡 */
    (void)spine_ik_test("/spine/spineboy-pro.skel",
                        "/spine/spineboy-pma.atlas",
                        "walk", 5, 1);
#endif""" + s[old_ik.end():]

    # 6) demo / 心跳
    s = s.replace("#if SPINE_RUN_DEMO\n    /* 自检全部通过后进入循环展示（不返回） */\n    spine_demo_run();\n#endif",
"""#if TEST_DEMO
    /* 6 场景循环展示（不返回） */
    spine_demo_run();
#endif

#if TEST_HEARTBEAT
    printf("heartbeat start\\r\\n");

    while (1)
    {
        LED0_TOGGLE();
        delay_ms(1000);
        beat++;
        printf("alive %lu\\r\\n", (unsigned long)beat);
    }
#endif""")

    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
    print("selftest.c: tests are now macro-guarded")


def add_to_project():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()

    if "spine_ik_test.c" in s:
        print("uvprojx: spine_ik_test.c already present")
        return

    m = re.search(r"[ \t]*<File>\s*<FileName>spine_demo\.c</FileName>.*?</File>", s, re.S)
    if not m:
        m = re.search(r"[ \t]*<File>\s*<FileName>selftest\.c</FileName>.*?</File>", s, re.S)

    block = """
            <File>
              <FileName>spine_ik_test.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\..\\User\\spine_ik_test.c</FilePath>
            </File>"""

    s = s[:m.end()] + block + s[m.end():]
    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)
    print("uvprojx: spine_ik_test.c added")


if __name__ == "__main__":
    strip_old_ik_test()
    patch_selftest()
    add_to_project()
