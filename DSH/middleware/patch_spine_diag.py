#!/usr/bin/env python3
"""Insert the spine render diagnostics printf into User/spine_test.cpp.

Line based (no string escaping) because several patch attempts through shell
heredocs mangled the \\r\\n escape sequences.

Run from the project root:  python DSH/middleware/patch_spine_diag.py
"""
import io

PATH = "User/spine_test.cpp"

DIAG = (
    '    printf("[SPN] diag: cmds=%d verts=%d nullTex=%d bbox=(%.0f,%.0f)-(%.0f,%.0f)\\r\\n",\n'
    '           g_cmds, g_verts, g_nulltex, g_minx, g_miny, g_maxx, g_maxy);\n'
)


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")

    if any("diag: cmds=" in ln for ln in lines):
        print("diag already present")
        return

    out = []
    inserted = False

    for ln in lines:
        if (not inserted) and ('printf("[SPN] %d frames' in ln):
            out.append(DIAG.rstrip("\n"))
            inserted = True
        out.append(ln)

    if not inserted:
        print("anchor not found")
        return

    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("diag printf inserted")


if __name__ == "__main__":
    main()
