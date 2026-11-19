#!/usr/bin/env python3
"""Wire the animation-transition test into the build and the boot flow.

  * uvprojx : add User/spine_anim_test.c
  * test_cfg: TEST_ANIM_MIX switch (default 1)
  * selftest: run it right after the IK test

Run from the project root:  python DSH/middleware/wire_anim_test.py
"""
import io
import re

PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"
CFG = "User/test_cfg.h"
SELFTEST = "User/selftest.c"


def add_file():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()

    if "spine_anim_test.c" in s:
        print("uvprojx: already present")
        return

    m = re.search(r"[ \t]*<File>\s*<FileName>spine_ik_test\.c</FileName>.*?</File>", s, re.S)
    if m is None:
        m = re.search(r"[ \t]*<File>\s*<FileName>selftest\.c</FileName>.*?</File>", s, re.S)

    block = """
            <File>
              <FileName>spine_anim_test.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\..\\User\\spine_anim_test.c</FilePath>
            </File>"""

    s = s[:m.end()] + block + s[m.end():]
    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)
    print("uvprojx: spine_anim_test.c added")


def add_switch():
    s = io.open(CFG, encoding="utf-8").read()

    if "TEST_ANIM_MIX" in s:
        print("test_cfg: already present")
        return

    s = s.replace("#endif /* __TEST_CFG_H */",
"""/** 动画衔接测试（过渡 / 排队 / 进度接回） */
#ifndef TEST_ANIM_MIX
#define TEST_ANIM_MIX        1
#endif

#endif /* __TEST_CFG_H */""")
    io.open(CFG, "w", encoding="utf-8", newline="").write(s)
    print("test_cfg: TEST_ANIM_MIX added")


def add_call():
    s = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_anim_test" in s:
        print("selftest: already wired")
        return

    s = s.replace('#include "spine_ik_test.h"',
                  '#include "spine_ik_test.h"\n#include "spine_anim_test.h"', 1)

    anchor = "#if TEST_DEMO"
    add = """#if TEST_ANIM_MIX
    /* 动画衔接：默认过渡 / 当前动画名 / 进度接回 / 排队下一段 */
    (void)spine_anim_test("/spine/spineboy-pro.skel",
                          "/spine/spineboy-pma.atlas", 30);
#endif

#if TEST_DEMO"""
    s = s.replace(anchor, add, 1)

    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
    print("selftest: animation test wired")


if __name__ == "__main__":
    add_file()
    add_switch()
    add_call()
