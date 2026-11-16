#!/usr/bin/env python3
"""Insert a framebuffer checksum print into User/spine_test.cpp (after the frame loop).

Lets us compare what the firmware believes it rendered with what OpenOCD dumps
from 0xC0000000.  If they differ, the dump is reading a different region than
the renderer writes.

Run from the project root:  python DSH/middleware/patch_spine_fbcheck.py
"""
import io

PATH = "User/spine_test.cpp"

BLOCK = [
    "    {",
    "        uint32_t sum = 0;",
    "",
    "        for (int i = 0; i < 1000; i++)",
    "        {",
    "            sum += s_surf.px[(size_t)i * 997u];",
    "        }",
    "",
    "        printf(\"[SPN] fb checksum=%08lX base=%p\\r\\n\", (unsigned long)sum, (void *)s_surf.px);",
    "    }",
    "",
]


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")

    if any("fb checksum=" in ln for ln in lines):
        print("already present")
        return

    out = []
    inserted = False

    for ln in lines:
        if (not inserted) and ln.startswith("    uint32_t cycles = DWT->CYCCNT - t0;"):
            for bl in BLOCK:
                out.append(bl)
            inserted = True
        out.append(ln)

    if not inserted:
        print("anchor not found")
        return

    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("fb checksum probe inserted")


if __name__ == "__main__":
    main()
