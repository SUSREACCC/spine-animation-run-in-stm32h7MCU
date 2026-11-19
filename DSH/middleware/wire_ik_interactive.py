#!/usr/bin/env python3
"""Wire the interactive IK test: touch stack + new module + switches.

  * uvprojx: add Drivers/BSP/TOUCH, IIC, 24CXX sources and User/spine_ik_interactive.c
  * test_cfg.h: TEST_TOUCH / TEST_IK_INTERACTIVE switches
  * selftest.c: tp_init() once, then run the interactive test when enabled

Run from the project root:  python DSH/middleware/wire_ik_interactive.py
"""
import io
import re

PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"
CFG = "User/test_cfg.h"
SELFTEST = "User/selftest.c"

DRV_FILES = [
    ("..\\..\\Drivers\\BSP\\TOUCH\\touch.c", "touch.c"),
    ("..\\..\\Drivers\\BSP\\TOUCH\\gt9xxx.c", "gt9xxx.c"),
    ("..\\..\\Drivers\\BSP\\TOUCH\\ft5206.c", "ft5206.c"),
    ("..\\..\\Drivers\\BSP\\TOUCH\\ctiic.c", "ctiic.c"),
    ("..\\..\\Drivers\\BSP\\IIC\\myiic.c", "myiic.c"),
    ("..\\..\\Drivers\\BSP\\24CXX\\24cxx.c", "24cxx.c"),
    ("..\\..\\User\\spine_ik_interactive.c", "spine_ik_interactive.c"),
]


def file_block(path, name):
    return """
            <File>
              <FileName>%s</FileName>
              <FileType>1</FileType>
              <FilePath>%s</FilePath>
            </File>""" % (name, path)


def patch_project():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()

    added = 0
    for path, name in DRV_FILES:
        if name in s:
            continue

        anchor = re.search(r"[ \t]*<File>\s*<FileName>spine_ik_test\.c</FileName>.*?</File>", s, re.S)
        if not anchor:
            anchor = re.search(r"[ \t]*<File>\s*<FileName>selftest\.c</FileName>.*?</File>", s, re.S)

        s = s[:anchor.end()] + file_block(path, name) + s[anchor.end():]
        added += 1

    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)
    print("uvprojx: %d file(s) added" % added)


def patch_cfg():
    s = io.open(CFG, encoding="utf-8").read()

    if "TEST_TOUCH" not in s:
        s = s.replace("""/*--------------------------------------------------------------------------- 兜底 */""",
"""/** 触摸屏（GT9xxx / FT5206 软 IIC，PB12/PB13） */
#ifndef TEST_TOUCH
#define TEST_TOUCH           1
#endif

/** 交互测试：点击屏幕驱动 IK 目标（需要 TEST_TOUCH） */
#ifndef TEST_IK_INTERACTIVE
#define TEST_IK_INTERACTIVE  1
#endif

/** 交互测试最长运行秒数（到点自动退出，避免一直占着板子） */
#ifndef TEST_IK_TOUCH_SECONDS
#define TEST_IK_TOUCH_SECONDS 180
#endif

/*--------------------------------------------------------------------------- 兜底 */""")
        io.open(CFG, "w", encoding="utf-8", newline="").write(s)
        print("test_cfg.h: touch switches added")


def patch_selftest():
    s = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_ik_interactive" not in s:
        s = s.replace('#include "spine_ik_test.h"',
                      '#include "spine_ik_test.h"\n#include "spine_ik_interactive.h"', 1)

        s = s.replace("""#if TEST_DEMO""",
"""#if TEST_IK_INTERACTIVE
    /* 交互：点击屏幕把 IK 目标挪到点击处 */
#if TEST_TOUCH
    printf("\\r\\n[IKT] tp_init() = %u\\r\\n", (unsigned)tp_init());
#else
    printf("\\r\\n[IKT] TEST_TOUCH=0，触摸未初始化\\r\\n");
#endif
    (void)spine_ik_interactive("/spine/spineboy-pro.skel",
                               "/spine/spineboy-pma.atlas",
                               "rear-leg-ik", TEST_IK_TOUCH_SECONDS);
#endif

#if TEST_DEMO""", 1)

        # touch.h 的 include（在 selftest 顶部）
        if '#include "touch.h"' not in s:
            s = s.replace('#include "test_cfg.h"', '#include "test_cfg.h"\n\n#if TEST_TOUCH\n#include "./BSP/TOUCH/touch.h"\n#endif', 1)

        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
        print("selftest.c: interactive test wired")


if __name__ == "__main__":
    patch_project()
    patch_cfg()
    patch_selftest()
