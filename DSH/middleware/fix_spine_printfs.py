#!/usr/bin/env python3
"""Repair any printf whose \\r\\n escape was turned into a real newline inside the
literal, in User/spine_test.cpp.

Generic: any line that ends with a double-quote-less tail (heuristic: the next
line starts with `", (` or `");`) is folded back together with a proper escape.

Run from the project root:  python DSH/middleware/fix_spine_printfs.py
"""
import io

PATH = "User/spine_test.cpp"
NL = "\\" + "r" + "\\" + "n"


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")
    out = []
    i = 0
    fixed = 0

    while i < len(lines):
        line = lines[i]
        nxt = lines[i + 1] if (i + 1) < len(lines) else ""

        # 形如  printf("....%d)
        #        ", args);
        if line.rstrip().endswith(")") is False and line.count('"') % 2 == 1 and nxt.lstrip().startswith('"'):
            merged = line.rstrip() + NL + nxt.lstrip()
            out.append(merged)
            i += 2
            fixed += 1
            continue

        out.append(line)
        i += 1

    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("repaired:", fixed)


if __name__ == "__main__":
    main()
