#!/usr/bin/env python3
"""Overlay API: sticky + cheap (corrected against the real spine_draw_end layout).

Baseline the demo queued the HUD every frame -> the frame dirty rect always
covered the full-width HUD bands -> the half-res upscaler ran over the whole
screen every frame (50 fps -> 32 fps).

New behaviour:
  * overlay ops keep their OWN bbox;
  * the bbox is merged into the frame dirty rect only when the overlay content
    changed (generation bump) AND this framebuffer has not picked it up yet;
  * per-buffer generations mean each of the 3 buffers refreshes once, then
    unchanged frames only re-rasterise the character area.

Run from the project root:  python DSH/middleware/patch_overlay_sticky.py
"""
import io

CPP = "User/spine_api.cpp"

OLD_DECLS = """static spine_ov_op_t g_ov[SPINE_OV_MAX];
static int           g_ov_count = 0;
"""

NEW_DECLS = """static spine_ov_op_t g_ov[SPINE_OV_MAX];
static spine_ov_op_t g_ov_prev[SPINE_OV_MAX];
static int           g_ov_count = 0;
static int           g_ov_prev_count = 0;
static uint32_t      g_ov_gen = 1;             /* 覆盖层内容代次 */
static int           g_ov_have_bbox = 0;
static int           g_ov_bx0, g_ov_by0, g_ov_bx1, g_ov_by1;
"""

OLD_BBOX = r'''/* 把一次覆盖层操作并入本帧脏矩形 */
static void ov_extend_bbox(int x0, int y0, int x1, int y1)
{
    if (!g_d.have_bbox)
    {
        g_d.fbx0 = x0;
        g_d.fby0 = y0;
        g_d.fbx1 = x1;
        g_d.fby1 = y1;
        g_d.have_bbox = 1;
        return;
    }

    if (x0 < g_d.fbx0) { g_d.fbx0 = x0; }
    if (y0 < g_d.fby0) { g_d.fby0 = y0; }
    if (x1 > g_d.fbx1) { g_d.fbx1 = x1; }
    if (y1 > g_d.fby1) { g_d.fby1 = y1; }
}'''

NEW_BBOX = r'''/* 覆盖层自己的包围盒（与帧脏矩形分开；内容没变就不并进去） */
static void ov_extend_bbox(int x0, int y0, int x1, int y1)
{
    if (!g_ov_have_bbox)
    {
        g_ov_bx0 = x0;
        g_ov_by0 = y0;
        g_ov_bx1 = x1;
        g_ov_by1 = y1;
        g_ov_have_bbox = 1;
        return;
    }

    if (x0 < g_ov_bx0) { g_ov_bx0 = x0; }
    if (y0 < g_ov_by0) { g_ov_by0 = y0; }
    if (x1 > g_ov_bx1) { g_ov_bx1 = x1; }
    if (y1 > g_ov_by1) { g_ov_by1 = y1; }
}'''


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "g_ov_gen" in s:
        print("already patched")
        return

    assert OLD_DECLS in s
    s = s.replace(OLD_DECLS, NEW_DECLS, 1)

    assert OLD_BBOX in s
    s = s.replace(OLD_BBOX, NEW_BBOX, 1)

    # draw_begin: 清覆盖层包围盒
    s = s.replace("""    g_ov_count = 0;
    g_d.have_bbox = 0;""",
"""    g_ov_count = 0;
    g_ov_have_bbox = 0;
    g_d.have_bbox = 0;""")

    # draw_end: 先判定是否需要重画覆盖层，并按需并入脏矩形
    old_head = """    int idx = g_d.draw_idx;
"""
    new_head = """    int idx = g_d.draw_idx;
    int ov_redraw = 0;

    /* ---- 覆盖层：内容变了才重画，并且每个缓冲只吸收一次 ---- */
    if (g_ov_count > 0)
    {
        int changed = (g_ov_count != g_ov_prev_count) ||
                      (memcmp(g_ov, g_ov_prev,
                              sizeof(spine_ov_op_t) * (size_t)g_ov_count) != 0);

        if (changed)
        {
            memcpy(g_ov_prev, g_ov, sizeof(spine_ov_op_t) * (size_t)g_ov_count);
            g_ov_prev_count = g_ov_count;
            g_ov_gen++;
        }

        if (g_d.buf_ov_gen[idx] != g_ov_gen)
        {
            ov_redraw = 1;
            g_d.buf_ov_gen[idx] = g_ov_gen;

            if (g_ov_have_bbox)
            {
                if (!g_d.have_bbox)
                {
                    g_d.fbx0 = g_ov_bx0;
                    g_d.fby0 = g_ov_by0;
                    g_d.fbx1 = g_ov_bx1;
                    g_d.fby1 = g_ov_by1;
                    g_d.have_bbox = 1;
                }
                else
                {
                    if (g_ov_bx0 < g_d.fbx0) { g_d.fbx0 = g_ov_bx0; }
                    if (g_ov_by0 < g_d.fby0) { g_d.fby0 = g_ov_by0; }
                    if (g_ov_bx1 > g_d.fbx1) { g_d.fbx1 = g_ov_bx1; }
                    if (g_ov_by1 > g_d.fby1) { g_d.fby1 = g_ov_by1; }
                }
            }
        }
    }
"""
    assert old_head in s
    s = s.replace(old_head, new_head, 1)

    # flush 改成按需
    old_flush = """    /* 覆盖层画在实例之上 */
    spine_overlay_flush(&g_d.surf, (g_d.divisor == 1) ? 1.0f : 0.5f);"""
    new_flush = """    /* 覆盖层画在实例之上（内容变了才重画） */
    if (ov_redraw)
    {
        spine_overlay_flush(&g_d.surf, (g_d.divisor == 1) ? 1.0f : 0.5f);
    }"""
    assert old_flush in s
    s = s.replace(old_flush, new_flush, 1)

    # g_d 增加每个缓冲的代次数组
    old_struct = """    uint16_t *bufs[3];"""
    new_struct = """    uint16_t *bufs[3];
    uint32_t         buf_ov_gen[3];              /* 每个缓冲已吸收的覆盖层代次 */"""
    assert old_struct in s
    s = s.replace(old_struct, new_struct, 1)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("overlay made sticky (per-buffer generation)")


if __name__ == "__main__":
    main()
