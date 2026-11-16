#!/usr/bin/env python3
"""Add the trimmed TGX 2D subset + its C++ self-test to STM32H743.uvprojx.

- new group "Middlewares/TGX": Color.cpp, Fonts.cpp   (FileType 8 = C++)
- new file in "User": tgx_selftest.cpp                (FileType 8 = C++)

Run from the project root:  python DSH/middleware/patch_add_tgx.py
(then run patch_cpp_file_options.py on the added .cpp files)
"""
import io

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"


def file_entry(name, path, ftype=8, indent="            "):
    return (f"{indent}<File>\n"
            f"{indent}  <FileName>{name}</FileName>\n"
            f"{indent}  <FileType>{ftype}</FileType>\n"
            f"{indent}  <FilePath>{path}</FilePath>\n"
            f"{indent}</File>\n")


GROUP = ("""        <Group>
          <GroupName>Middlewares/TGX</GroupName>
          <Files>
"""
          + file_entry("Color.cpp", r"..\..\Middlewares\TGX\Color.cpp")
          + file_entry("Fonts.cpp", r"..\..\Middlewares\TGX\Fonts.cpp")
          + """          </Files>
        </Group>
""")


def main():
    s = io.open(PATH, encoding="latin-1").read()

    added = 0

    if "<GroupName>Middlewares/TGX</GroupName>" not in s:
        s = s.replace("      </Groups>", GROUP + "      </Groups>", 1)
        added += 2

    if "tgx_selftest.cpp" not in s:
        i = s.index("<GroupName>User</GroupName>")
        j = s.index("          </Files>", i)
        s = s[:j] + file_entry("tgx_selftest.cpp", r"..\..\User\tgx_selftest.cpp") + s[j:]
        added += 1

    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print(f"uvprojx: {added} file entries added (TGX group + tgx_selftest.cpp)")


if __name__ == "__main__":
    main()
