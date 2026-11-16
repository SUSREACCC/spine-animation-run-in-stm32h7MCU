#!/usr/bin/env python3
"""Clean up: remove the 3-frame [DBG] block from spine_play and set the self-test
to run a 4 s full-res benchmark followed by a 12 s half-res playback.

Run from the project root:  python DSH/middleware/patch_spine_cleanup.py
"""
import io

PATH = "User/spine_test.cpp"
SELFTEST = "User/selftest.c"


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")

    start = None
    for i, ln in enumerate(lines):
        if "if (dbg_this)" in ln:
            start = i
            break

    if start is not None:
        end = None
        for j in range(start, min(start + 30, len(lines))):
            if "dst[(size_t)(2 * dby0) * SCR_W + 2 * dbx0]);" in lines[j]:
                end = j + 1          # include the closing brace line
                break
        if end is None:
            raise SystemExit("debug block end not found")

        # 同时删掉 `bool dbg_this = ...;` 那行和后面的空行
        del lines[start:end]

        for i, ln in enumerate(lines):
            if "bool dbg_this" in ln:
                del lines[i]
                break

        io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(lines))
        print("debug block removed")
    else:
        print("no debug block")

    c = io.open(SELFTEST, encoding="utf-8").read()
    old = '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 6, 2);'
    new = ('    /* 全分辨率基准 4s + 半分辨率播放 12s */\n'
           '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 4, 1);\n'
           '    (void)spine_play("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas", "walk", 60, 12, 2);')
    if old in c:
        c = c.replace(old, new, 1)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("selftest: full-res 4s + half-res 12s")


if __name__ == "__main__":
    main()
