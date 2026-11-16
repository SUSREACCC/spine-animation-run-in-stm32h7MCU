#!/usr/bin/env python3
"""Re-insert the clear_rect() and commands_bbox() helpers that were removed
together with the old two-buffer spine_play().

Run from the project root:  python DSH/middleware/patch_spine_restore_helpers.py
"""
import io

PATH = "User/spine_test.cpp"

HELPERS = r'''
static void clear_rect(raster_surface_t *s, int x0, int y0, int x1, int y1, uint16_t color)
{
    if (x0 < s->clip_x0) { x0 = s->clip_x0; }
    if (y0 < s->clip_y0) { y0 = s->clip_y0; }
    if (x1 > s->clip_x1) { x1 = s->clip_x1; }
    if (y1 > s->clip_y1) { y1 = s->clip_y1; }
    if ((x0 > x1) || (y0 > y1)) { return; }

    for (int y = y0; y <= y1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        for (int x = x0; x <= x1; x++)
        {
            row[x] = color;
        }
    }
}

/* 由渲染命令计算屏幕包围盒（真实顶点，不是 setup pose） */
static void commands_bbox(spine::RenderCommand *cmd, float scale, float ox, float oy,
                          int *bx0, int *by0, int *bx1, int *by1)
{
    float minx = 1e9f, maxx = -1e9f, miny = 1e9f, maxy = -1e9f;

    while (cmd != nullptr)
    {
        for (int i = 0; i < cmd->numVertices; i++)
        {
            float x = cmd->positions[2 * i + 0] * scale + ox;
            float y = cmd->positions[2 * i + 1] * scale + oy;

            if (x < minx) { minx = x; }
            if (x > maxx) { maxx = x; }
            if (y < miny) { miny = y; }
            if (y > maxy) { maxy = y; }
        }
        cmd = cmd->next;
    }

    if (maxx < minx)
    {
        *bx0 = *by0 = 0;
        *bx1 = *by1 = -1;
        return;
    }

    *bx0 = (int)floorf(minx) - 2;
    *by0 = (int)floorf(miny) - 2;
    *bx1 = (int)ceilf(maxx) + 2;
    *by1 = (int)ceilf(maxy) + 2;
}

'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "static void clear_rect" in s:
        print("helpers already present")
        return

    marker = "/*----------------------------------------------------------------- 实时播放（三缓冲） */"

    if marker not in s:
        raise SystemExit("playback marker not found")

    s = s.replace(marker, HELPERS.strip() + "\n\n" + marker, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("helpers restored")


if __name__ == "__main__":
    main()
