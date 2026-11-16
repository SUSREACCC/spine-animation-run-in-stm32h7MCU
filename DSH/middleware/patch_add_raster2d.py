#!/usr/bin/env python3
"""Add the raster2d middleware + its regression test to STM32H743.uvprojx.

Run from the project root:
    python DSH/middleware/patch_add_raster2d.py
    python DSH/middleware/rebuild_cpp_entries.py      (adds the C++17 file options)
"""
import io

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"

GROUP = """        <Group>
          <GroupName>Middlewares/RASTER</GroupName>
          <Files>
            <File>
              <FileName>raster2d.cpp</FileName>
              <FileType>8</FileType>
              <FilePath>..\\..\\Middlewares\\RASTER\\raster2d.cpp</FilePath>
            </File>
          </Files>
        </Group>
"""

USER_ENTRY = """            <File>
              <FileName>raster_test.cpp</FileName>
              <FileType>8</FileType>
              <FilePath>..\\..\\User\\raster_test.cpp</FilePath>
            </File>
"""


def main():
    s = io.open(PATH, encoding="latin-1").read()
    added = []

    if "<GroupName>Middlewares/RASTER</GroupName>" not in s:
        s = s.replace("      </Groups>", GROUP + "      </Groups>", 1)
        added.append("group Middlewares/RASTER")

    if "raster_test.cpp" not in s:
        i = s.index("<GroupName>User</GroupName>")
        j = s.index("          </Files>", i)
        s = s[:j] + USER_ENTRY + s[j:]
        added.append("raster_test.cpp")

    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("added:", ", ".join(added) if added else "(nothing)")


if __name__ == "__main__":
    main()
