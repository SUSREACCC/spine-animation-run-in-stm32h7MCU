#!/usr/bin/env python3
"""Wire the 4-phase animation sequence test.

  * uvprojx : add User/spine_anim_seq.c and User/spine_touch.c
  * test_cfg: TEST_ANIM_SEQ (default 1)
  * selftest: run it after the IK test, before the (endless) interactive test

Run from the project root:  python DSH/middleware/wire_anim_seq.py
"""
import io
import re

PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"
CFG = "User/test_cfg.h"
SELFTEST = "User/selftest.c"

FILES = [
    ("..\\..\\User\\spine_touch.c", "spine_touch.c"),
    ("..\\..\\User\\spine_anim_seq.c", "spine_anim_seq.c"),
]


def add_files():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()
    added = 0

    for path, name in FILES:
        if name in s:
            continue

        m = re.search(r"[ \t]*<File>\s*<FileName>spine_anim_test\.c</FileName>.*?</File>", s, re.S)
        if m is None:
            m = re.search(r"[ \t]*<File>\s*<FileName>selftest\.c</FileName>.*?</File>", s, re.S)

        block = """
            <File>
              <FileName>%s</FileName>
              <FileType>1</FileType>
              <FilePath>%s</FilePath>
            </File>""" % (name, path)

        s = s[:m.end()] + block + s[m.end():]
        added += 1

    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)
    print("uvprojx: %d file(s) added" % added)


def add_switch():
    s = io.open(CFG, encoding="utf-8").read()

    if "TEST_ANIM_SEQ" in s:
        print("test_cfg: already present")
        return

    s = s.replace("#endif /* __TEST_CFG_H */",
"""/** 动画序列：walk 5s -> idle 5s -> aim 10s(触摸驱动 aim-ik) -> death 5s(单次) */
#ifndef TEST_ANIM_SEQ
#define TEST_ANIM_SEQ        1
#endif

#endif /* __TEST_CFG_H */""")
    io.open(CFG, "w", encoding="utf-8", newline="").write(s)
    print("test_cfg: TEST_ANIM_SEQ added")


def add_call():
    s = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_anim_seq" in s:
        print("selftest: already wired")
        return

    s = s.replace('#include "spine_anim_test.h"',
                  '#include "spine_anim_test.h"\n#include "spine_anim_seq.h"', 1)

    anchor = "#if TEST_IK_INTERACTIVE"
    add = """#if TEST_ANIM_SEQ
    /* 4 段动画序列；aim 段触摸驱动 aim-ik */
    (void)spine_anim_seq("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas");
#endif

#if TEST_IK_INTERACTIVE"""
    s = s.replace(anchor, add, 1)

    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
    print("selftest: animation sequence wired")


if __name__ == "__main__":
    add_files()
    add_switch()
    add_call()
