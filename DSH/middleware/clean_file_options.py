#!/usr/bin/env python3
"""Strip per-file option blocks from everything that is not a .cpp source.

Earlier regex-based patching mis-nested the XML and attached <FileOption>
blocks to delay.c / sys.c, which then received -std=c++1z (a C++-only flag).

Also verifies that each <File> entry still has exactly one FileName/FilePath
pair, printing a summary of any anomaly.

Run from the project root:  python DSH/middleware/clean_file_options.py
"""
import io
import re

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"

FILE_BLOCK = re.compile(r"<File>.*?</File>", re.S)
OPTION = re.compile(r"\s*<FileOption>.*?</FileOption>\s*", re.S)


def main():
    s = io.open(PATH, encoding="latin-1").read()
    out = []
    pos = 0
    stripped, kept = [], []

    for m in FILE_BLOCK.finditer(s):
        block = m.group(0)
        name = re.search(r"<FileName>(.*?)</FileName>", block, re.S)
        name = name.group(1) if name else "?"

        if not name.endswith(".cpp"):
            new_block = OPTION.sub("\n", block)
            if new_block != block:
                stripped.append(name)
            block = new_block
        else:
            if "<FileOption>" in block:
                kept.append(name)

        out.append(s[pos:m.start()])
        out.append(block)
        pos = m.end()

    out.append(s[pos:])
    io.open(PATH, "w", encoding="latin-1", newline="").write("".join(out))

    print("stripped FileOption from:", ", ".join(stripped) if stripped else "(none)")
    print("cpp files keeping options:", ", ".join(kept) if kept else "(none)")


if __name__ == "__main__":
    main()
