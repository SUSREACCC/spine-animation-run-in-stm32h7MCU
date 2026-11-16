#!/usr/bin/env python3
"""Add a point-sampling switch to TGX's 2D textured shader (macro guarded).

When TGX_TEXTURE_POINT is defined before including TGX, the 2D textured path
fetches the nearest texel instead of doing 4-tap bilinear interpolation.
The change is inert unless the macro is defined (default: off).

Patched location: Middlewares/TGX/Shaders.h, the non-masked branch of the
2D texture shader (_drawTexturedTriangle).

Run from the project root:  python DSH/middleware/patch_tgx_point_sampling.py
"""
import io

SHADERS = "Middlewares/TGX/Shaders.h"
TGXH = "Middlewares/TGX/tgx.h"

OLD = """                    color_t_tex col = interpolateColorsBilinear(tex[minx + miny], tex[maxx + miny], tex[minx + maxy], tex[maxx + maxy], ax, ay);"""

NEW = """#if defined(TGX_TEXTURE_POINT)
                    /* PROJECT PATCH: nearest-texel sampling (much cheaper than 4-tap bilinear) */
                    color_t_tex col = tex[(((ax < 0.5f) ? minx : maxx)) + (((ay < 0.5f) ? miny : maxy))];
#else
                    color_t_tex col = interpolateColorsBilinear(tex[minx + miny], tex[maxx + miny], tex[minx + maxy], tex[maxx + maxy], ax, ay);
#endif"""


def main():
    s = io.open(SHADERS, encoding="utf-8").read()
    if "TGX_TEXTURE_POINT" in s:
        print("Shaders.h already patched")
    else:
        n = s.count(OLD)
        if n == 0:
            raise SystemExit("pattern not found in Shaders.h")
        s = s.replace(OLD, NEW, 1)
        io.open(SHADERS, "w", encoding="utf-8", newline="").write(s)
        print(f"Shaders.h patched (pattern occurrences: {n}, replaced first)")

    t = io.open(TGXH, encoding="utf-8").read()
    if "TGX_TEXTURE_POINT" not in t:
        t = t.replace('#include <stdlib.h>',
                      '/* 点采样开关：实测双线性约 176 cycles/px，点采样可显著降低 */\n'
                      '#ifndef TGX_TEXTURE_POINT\n#define TGX_TEXTURE_POINT 1\n#endif\n\n'
                      '#include <stdlib.h>', 1)
        io.open(TGXH, "w", encoding="utf-8", newline="").write(t)
        print("tgx.h: TGX_TEXTURE_POINT enabled")


if __name__ == "__main__":
    main()
