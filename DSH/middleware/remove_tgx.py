#!/usr/bin/env python3
"""Remove TGX entirely from a project.

TGX is only used by tgx_selftest.cpp (a 2D benchmark).  The production render
path is raster2d, so TGX costs ~60 KB of flash for nothing after the benchmark
numbers were recorded in docs/.

Removes:
  * Middlewares/TGX/            (18 files)
  * User/tgx_selftest.cpp/.h
  * the "Middlewares/TGX" group in the uvprojx (with its include path)
  * the tgx_selftest() call and RESULT line in selftest.c

Usage (from the project root):  python DSH/middleware/remove_tgx.py
"""
import io
import os
import re
import shutil

PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"
SELFTEST = "User/selftest.c"
TGX_DIR = "Middlewares/TGX"
TGX_SRC = ["User/tgx_selftest.cpp", "User/tgx_selftest.h"]


def remove_files():
    if os.path.isdir(TGX_DIR):
        shutil.rmtree(TGX_DIR)
        print("removed", TGX_DIR)

    for f in TGX_SRC:
        if os.path.isfile(f):
            os.remove(f)
            print("removed", f)


def patch_project():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()

    # 1) 删掉整个 TGX 组
    m = re.search(r"[ \t]*<Group>\s*<GroupName>Middlewares/TGX</GroupName>.*?</Group>\s*", s, re.S)
    if m:
        s = s[:m.start()] + s[m.end():]
        print("uvprojx: TGX group removed")
    else:
        print("uvprojx: TGX group not found")

    # 2) 删掉 include 路径里的 ..\..\Middlewares\TGX
    s = re.sub(r"\.\.\\\.\.\\Middlewares\\TGX;?", "", s)
    print("uvprojx: TGX include path removed")

    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)


def patch_selftest():
    s = io.open(SELFTEST, encoding="utf-8").read()

    s = s.replace('#include "tgx_selftest.h"\n', "")
    s = s.replace("static uint8_t  g_rc_tgx   = ST_PENDING;\n", "")

    # 调用与打印
    s = s.replace("""    g_rc_tgx = tgx_selftest();
    printf("RESULT TGX=%s\\r\\n", rc_str(g_rc_tgx));
""", "")

    # 汇总行里去掉 TGX= 段（如果有）
    s = s.replace('RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s FATFS=%s', 'RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s FATFS=%s')

    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
    print("selftest.c: TGX call removed")


def main():
    remove_files()
    patch_project()
    patch_selftest()


if __name__ == "__main__":
    main()
