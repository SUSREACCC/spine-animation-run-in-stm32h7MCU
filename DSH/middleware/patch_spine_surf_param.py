#!/usr/bin/env python3
"""Fix: draw_commands() must render into the caller's surface, not the global.

In the half-res path we built a local raster_surface_t (400x240) but
draw_commands() still called raster_mesh(&s_surf, ...) with the global surface,
so the character was drawn into the full-size framebuffer (with the half-res
transform -> a small sprite in the top-left corner) while the low-res buffer only
ever received the clear colour.  The upscale then copied background into
buffers 1 and 2, which is exactly the ghosting / flicker / missing-layer mess.

Run from the project root:  python DSH/middleware/patch_spine_surf_param.py
"""
import io

PATH = "User/spine_test.cpp"


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "raster_surface_t *surf)" in s:
        print("already patched")
        return

    old_sig = "static void draw_commands(spine::RenderCommand *cmd, float scale, float ox, float oy)"
    new_sig = "static void draw_commands(spine::RenderCommand *cmd, float scale, float ox, float oy,\n                           raster_surface_t *surf)"
    if old_sig not in s:
        raise SystemExit("draw_commands signature not found")
    s = s.replace(old_sig, new_sig, 1)

    old_call = "            raster_mesh(&s_surf, &rt, verts, n, cmd->indices, cmd->numIndices,\n                        (raster_blend_t)blend_of(cmd->blendMode), 255);"
    new_call = "            raster_mesh(surf, &rt, verts, n, cmd->indices, cmd->numIndices,\n                        (raster_blend_t)blend_of(cmd->blendMode), 255);"
    if old_call not in s:
        raise SystemExit("raster_mesh call not found")
    s = s.replace(old_call, new_call, 1)

    # 调用点：sheet 用全局 s_surf，playback 用局部 rs
    n = s.count("draw_commands(cmd, cell_scale, ox, oy);")
    s = s.replace("draw_commands(cmd, cell_scale, ox, oy);",
                  "draw_commands(cmd, cell_scale, ox, oy, &s_surf);")

    m = s.count("draw_commands(cmd_list, scale, ox, oy);")
    s = s.replace("draw_commands(cmd_list, scale, ox, oy);",
                  "draw_commands(cmd_list, scale, ox, oy, &rs);")

    k = s.count("draw_commands(renderer.render(skeleton), cell_scale, ox, oy);")
    s = s.replace("draw_commands(renderer.render(skeleton), cell_scale, ox, oy);",
                  "draw_commands(renderer.render(skeleton), cell_scale, ox, oy, &s_surf);")

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("draw_commands now takes a surface (sheet:%d play:%d extra:%d)" % (n, m, k))


if __name__ == "__main__":
    main()
