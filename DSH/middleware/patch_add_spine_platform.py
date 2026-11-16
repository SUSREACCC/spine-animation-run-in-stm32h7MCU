#!/usr/bin/env python3
"""Add User/spine_platform.cpp (C++) to the User group.

Run from the project root:  python DSH/middleware/patch_add_spine_platform.py
(then run rebuild_cpp_entries.py so it gets the C++17 flags)
"""
import io

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"

ENTRY = (
    "            <File>\n"
    "              <FileName>spine_platform.cpp</FileName>\n"
    "              <FileType>8</FileType>\n"
    "              <FilePath>..\\..\\User\\spine_platform.cpp</FilePath>\n"
    "            </File>\n"
)


def main():
    s = io.open(PATH, encoding="latin-1").read()

    if "spine_platform.cpp" in s:
        print("already present")
        return

    i = s.index("<GroupName>User</GroupName>")
    j = s.index("          </Files>", i)
    s = s[:j] + ENTRY + s[j:]
    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("spine_platform.cpp added to User group")


if __name__ == "__main__":
    main()
