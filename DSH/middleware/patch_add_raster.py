#!/usr/bin/env python3
"""Add User/raster_probe.cpp (C++ source) to STM32H743.uvprojx.

Run from the project root:  python DSH/middleware/patch_add_raster.py
(then run patch_cpp_file_options.py raster_probe.cpp)
"""
import io

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"

ENTRY = (
    "            <File>\n"
    "              <FileName>raster_probe.cpp</FileName>\n"
    "              <FileType>8</FileType>\n"
    "              <FilePath>..\\..\\User\\raster_probe.cpp</FilePath>\n"
    "            </File>\n"
)


def main():
    s = io.open(PATH, encoding="latin-1").read()
    if "raster_probe.cpp" in s:
        print("already present")
        return

    i = s.index("<GroupName>User</GroupName>")
    j = s.index("          </Files>", i)
    s = s[:j] + ENTRY + s[j:]
    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("raster_probe.cpp added to the User group")


if __name__ == "__main__":
    main()
