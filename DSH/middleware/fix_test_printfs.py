#!/usr/bin/env python3
"""Repair printf statements whose \\r\\n escape was turned into a real newline
inside the string literal (happens when a patch goes through several layers of
shell escaping).  Any line that ends with `Mpx/s` and is followed by a line that
starts with `", (` is folded back into one statement with a proper escape.

Run from the project root:  python DSH/middleware/fix_test_printfs.py
"""
import io
import re

PATH = "User/raster_test.cpp"
NEWLINE = "\\" + "r" + "\\" + "n"


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")
    out = []
    i = 0
    fixed = 0

    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if (i + 1) < len(lines) else ""

        if line.rstrip().endswith("Mpx/s") and nxt.lstrip().startswith('", ('):
            merged = line.rstrip() + NEWLINE + nxt.lstrip()
            out.append(merged)
            i += 2
            fixed += 1
            continue

        out.append(line)
        i += 1

    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("repaired printf statements:", fixed)


if __name__ == "__main__":
    main()
