#!/usr/bin/env python3
"""Switch STM32H743.uvprojx from ARM Compiler 5 to ARM Compiler 6 (AC6).

- sets <uAC6>1 and updates <pCCUsed>
- inserts User/cpp_probe.cpp (FileType 8 = C++ source) into the User group

Run from the project root:  python DSH/middleware/patch_switch_ac6.py
"""
import io

PATH = "Projects/MDK-ARM/STM32H743.uvprojx"

PROBE_ENTRY = (
    "            <File>\n"
    "              <FileName>cpp_probe.cpp</FileName>\n"
    "              <FileType>8</FileType>\n"
    "              <FilePath>..\\..\\User\\cpp_probe.cpp</FilePath>\n"
    "            </File>\n"
)


def main():
    s = io.open(PATH, encoding="latin-1").read()

    s = s.replace("<uAC6>0</uAC6>", "<uAC6>1</uAC6>", 1)
    s = s.replace(
        "<pCCUsed>5060960::V5.06 update 7 (build 960)::.\\ARMCC</pCCUsed>",
        "<pCCUsed>6060750::V6.7::.\\ARMCLANG</pCCUsed>",
        1,
    )

    if "cpp_probe.cpp" not in s:
        i = s.index("<GroupName>User</GroupName>")
        j = s.index("          </Files>", i)
        s = s[:j] + PROBE_ENTRY + s[j:]

    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("uvprojx: uAC6 =", "1" if "<uAC6>1</uAC6>" in s else "0", "| probe entry:",
          "yes" if "cpp_probe.cpp" in s else "no")


if __name__ == "__main__":
    main()
