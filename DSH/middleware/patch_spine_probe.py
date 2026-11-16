#!/usr/bin/env python3
"""Insert a one-shot texture sampling probe into User/spine_test.cpp.

Prints, for the very first vertex of the first command: its UV in texels, the
raw ARGB1555 texel fetched at that position, the decoded RGB, and the vertex
tint colour.  Used to tell apart "wrong texture data" from "wrong decoding" and
"wrong vertex colour".

Run from the project root:  python DSH/middleware/patch_spine_probe.py
"""
import io

PATH = "User/spine_test.cpp"

PROBE = r'''            static int probed = 0;

            if (probed == 0)
            {
                probed = 1;

                int pu = (int)verts[0].u;
                int pv = (int)verts[0].v;

                if (pu < 0) { pu = 0; }
                if (pu >= tex->w) { pu = tex->w - 1; }
                if (pv < 0) { pv = 0; }
                if (pv >= tex->h) { pv = tex->h - 1; }

                unsigned raw = tex->px[pv * tex->w + pu];
                unsigned rr = (raw >> 10) & 0x1F;
                unsigned gg = (raw >> 5) & 0x1F;
                unsigned bb = raw & 0x1F;

                printf("[SPN] probe: uv=(%.1f,%.1f)px texel=%04X a=%u rgb555=(%u,%u,%u) tint=%08X\r\n",
                       verts[0].u, verts[0].v, raw, (raw >> 15) & 1, rr, gg, bb, verts[0].color);
            }

'''


def main():
    lines = io.open(PATH, encoding="utf-8").read().split("\n")

    if any("probe: uv=" in ln for ln in lines):
        print("probe already present")
        return

    out = []
    inserted = False

    for ln in lines:
        out.append(ln)
        if (not inserted) and ("raster_texture_t rt;" in ln):
            for pl in PROBE.rstrip("\n").split("\n"):
                out.append(pl)
            inserted = True

    if not inserted:
        print("anchor 'raster_texture_t rt;' not found")
        return

    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(out))
    print("probe inserted")


if __name__ == "__main__":
    main()
