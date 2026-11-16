#!/usr/bin/env python3
"""Make the playback dirty rect per-frame (union with the previous frame).

The old code derived the clear rectangle once from the setup-pose bounding box,
so anything the animation moved outside it was never cleared.  With double
buffering those stale pixels differed between the two buffers, which showed up
as trails plus flicker.

Run from the project root:  python DSH/middleware/patch_spine_bbox_perframe.py
"""
import io

PATH = "User/spine_test.cpp"

HELPER = r'''
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

    if "commands_bbox" in s:
        print("already patched")
        return

    anchor = 'static void clear_rect(raster_surface_t *s,'
    if anchor not in s:
        raise SystemExit("clear_rect anchor not found")
    s = s.replace(anchor, HELPER.strip() + "\n\n" + anchor, 1)

    # 删掉只用 setup pose 算一次的固定矩形
    old_rect = """    /* 角色在屏幕上的包围盒（用于局部清屏，省掉 70% 的清屏像素） */
    int bx0 = (int)(wminx * scale + ox) - 4;
    int by0 = (int)(wminy * scale + oy) - 4;
    int bx1 = (int)(wmaxx * scale + ox) + 4;
    int by1 = (int)(wmaxy * scale + oy) + 4;

    printf("[SPN] dirty rect: (%d,%d)-(%d,%d) = %d%% of screen\\r\\n",
           bx0, by0, bx1, by1,
           (int)(100.0f * (float)((bx1 - bx0 + 1) * (by1 - by0 + 1)) / (float)(SCR_W * SCR_H)));
"""
    new_rect = """    /* 上一帧的包围盒（第一帧为空），每帧与当前帧取并集做局部清屏 */
    int pbx0 = 0, pby0 = 0, pbx1 = -1, pby1 = -1;
"""
    if old_rect not in s:
        raise SystemExit("fixed rect block not found")
    s = s.replace(old_rect, new_rect, 1)

    old_loop = """        uint32_t tc0 = DWT->CYCCNT;

        clear_rect(&s_surf, bx0, by0, bx1, by1, 0x0861u);

        uint32_t tc1 = DWT->CYCCNT;

        draw_commands(renderer.render(skeleton), scale, ox, oy);

        uint32_t tc2 = DWT->CYCCNT;"""
    new_loop = """        uint32_t tc0 = DWT->CYCCNT;

        spine::RenderCommand *cmd_list = renderer.render(skeleton);

        /* 当前帧包围盒 + 上一帧包围盒 = 需要清的脏矩形 */
        int cbx0, cby0, cbx1, cby1;

        commands_bbox(cmd_list, scale, ox, oy, &cbx0, &cby0, &cbx1, &cby1);

        int dbx0 = (pbx1 < 0) ? cbx0 : ((cbx0 < pbx0) ? cbx0 : pbx0);
        int dby0 = (pby1 < 0) ? cby0 : ((cby0 < pby0) ? cby0 : pby0);
        int dbx1 = (pbx1 < 0) ? cbx1 : ((cbx1 > pbx1) ? cbx1 : pbx1);
        int dby1 = (pby1 < 0) ? cby1 : ((cby1 > pby1) ? cby1 : pby1);

        clear_rect(&s_surf, dbx0, dby0, dbx1, dby1, 0x0861u);

        uint32_t tc1 = DWT->CYCCNT;

        draw_commands(cmd_list, scale, ox, oy);

        pbx0 = cbx0; pby0 = cby0; pbx1 = cbx1; pby1 = cby1;

        uint32_t tc2 = DWT->CYCCNT;"""
    if old_loop not in s:
        raise SystemExit("loop block not found")
    s = s.replace(old_loop, new_loop, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("per-frame dirty rect installed")


if __name__ == "__main__":
    main()
