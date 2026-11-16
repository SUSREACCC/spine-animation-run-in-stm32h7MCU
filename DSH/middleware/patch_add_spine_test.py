#!/usr/bin/env python3
"""Add User/spine_test.cpp to the project and call the integration test from the
boot self-test (after the TGX test).

Run from the project root:
    python DSH/middleware/patch_add_spine_test.py
    python DSH/middleware/rebuild_cpp_entries.py
"""
import io

PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"
SELFTEST = "User/selftest.c"

ENTRY = (
    "            <File>\n"
    "              <FileName>spine_test.cpp</FileName>\n"
    "              <FileType>8</FileType>\n"
    "              <FilePath>..\\..\\User\\spine_test.cpp</FilePath>\n"
    "            </File>\n"
)

CALL = (
    '\n    /* ---- Spine 集成测试（素材需放在 SD 卡 /spine/ 下）---- */\n'
    '    (void)spine_test_run("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "run", 30);\n'
)


def main():
    s = io.open(PROJ, encoding="latin-1").read()

    if "spine_test.cpp" not in s:
        i = s.index("<GroupName>User</GroupName>")
        j = s.index("          </Files>", i)
        s = s[:j] + ENTRY + s[j:]
        io.open(PROJ, "w", encoding="latin-1", newline="").write(s)
        print("spine_test.cpp added")

    c = io.open(SELFTEST, encoding="utf-8").read()

    if "spine_test_run" not in c:
        if '#include "tgx_selftest.h"' in c:
            c = c.replace('#include "tgx_selftest.h"',
                          '#include "tgx_selftest.h"\n#include "spine_test.h"', 1)
        else:
            c = c.replace('#include "selftest.h"', '#include "selftest.h"\n#include "spine_test.h"', 1)

        c = c.rstrip()
        idx = c.rfind("}")
        c = c[:idx] + CALL + "}\n"
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("spine_test_run wired into selftest.c")


if __name__ == "__main__":
    main()
