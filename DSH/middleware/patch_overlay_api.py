#!/usr/bin/env python3
"""Add an overlay API to spine_api: draw HUD / UI / debug graphics into the SAME
render target as the spine layer, so they ride the triple-buffer + dirty-rect
pipeline and stay consistent at any divisor.

Why not use the board's lcd_fill/lcd_show_string:
  * lcd_fill() goes through DMA2D -> different cache view than our CPU draws
  * lcd_show_string() uses mode=0 (paints background) with the global
    g_back_color, whose default is white -> white-on-white
  * neither knows about our 3 framebuffers or the half-res scaling

New API (spine_api.h):

    void spine_overlay_rect (int x0, int y0, int x1, int y1, uint16_t color565);
    void spine_overlay_frame(int x0, int y0, int x1, int y1, int thick, uint16_t color565);
    void spine_overlay_text (int x, int y, const char *ascii, uint16_t color565);

Coordinates are screen pixels (same space as spine_instance_set_position).
Ops are queued and flushed by spine_draw_end(), after the spine instances.
Queuing an op also extends the frame dirty-rect so it gets upscaled/cleared.

Run from the project root:  python DSH/middleware/patch_overlay_api.py
"""
import io

H = "User/spine_api.h"
CPP = "User/spine_api.cpp"

H_ADD = r'''
/*==================================================================================================
 * 覆盖层（HUD / UI / 调试）
 *
 * 与 spine 层画进同一块渲染目标，因此：
 *   - 跟随三缓冲，不会闪烁
 *   - 坐标用屏幕像素，半分辨率时自动按 divisor 展开（每个字形像素变成 divisor×divisor 块）
 *   - 会扩展脏矩形，保证被放大与清除
 *
 * 用法：spine_draw_begin() 之后、spine_draw_end() 之前调用（顺序无所谓，
 *       覆盖层总是画在所有 spine 实例之上）。
 *=================================================================================================*/

/** 实心矩形（屏幕像素，闭区间） */
void spine_overlay_rect(int x0, int y0, int x1, int y1, uint16_t color565);

/** 矩形边框 */
void spine_overlay_frame(int x0, int y0, int x1, int y1, int thick, uint16_t color565);

/** 16 px 高 ASCII 文本（复用板级 asc2_1608 字库） */
void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565);

/** 本帧已排队的覆盖层操作数（诊断） */
int spine_overlay_count(void);
'''

CPP_ADD = r'''
/*----------------------------------------------------------------- 覆盖层 */

#define SPINE_OV_MAX      32
#define SPINE_OV_TEXT_MAX 48

typedef struct
{
    uint8_t  type;                 /* 0=矩形 1=边框 2=文本 */
    int16_t  x0, y0, x1, y1;
    int16_t  thick;
    uint16_t color;
    char     text[SPINE_OV_TEXT_MAX];
} spine_ov_op_t;

static spine_ov_op_t g_ov[SPINE_OV_MAX];
static int           g_ov_count = 0;

int spine_overlay_count(void)
{
    return g_ov_count;
}

/* 把一块 divisor×divisor 的像素写进 surface（半分辨率时一个屏幕像素 = 一块） */
static void ov_block(raster_surface_t *s, int sx, int sy, int n, uint16_t color)
{
    int x1 = sx + n - 1;
    int y1 = sy + n - 1;

    if (sx < s->clip_x0) { sx = s->clip_x0; }
    if (sy < s->clip_y0) { sy = s->clip_y0; }
    if (x1 > s->clip_x1) { x1 = s->clip_x1; }
    if (y1 > s->clip_y1) { y1 = s->clip_y1; }
    if ((sx > x1) || (sy > y1)) { return; }

    for (int y = sy; y <= y1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        for (int x = sx; x <= x1; x++)
        {
            row[x] = color;
        }
    }
}

/* 屏幕像素矩形 -> surface 上的填充 */
static void ov_rect_scaled(raster_surface_t *s, float inv,
                           int x0, int y0, int x1, int y1, uint16_t color)
{
    int n = (inv > 1.5f) ? 2 : 1;
    int sx0 = (int)((float)x0 * inv);
    int sy0 = (int)((float)y0 * inv);
    int sx1 = (int)((float)(x1 + 1) * inv) - 1;
    int sy1 = (int)((float)(y1 + 1) * inv) - 1;

    if (n == 1)
    {
        ov_block(s, sx0, sy0, 1, color);
        return;
    }

    for (int y = sy0; y <= sy1; y++)
    {
        uint16_t *row = s->px + (size_t)y * s->stride;

        if ((y < s->clip_y0) || (y > s->clip_y1)) { continue; }

        for (int x = sx0; x <= sx1; x++)
        {
            if ((x >= s->clip_x0) && (x <= s->clip_x1))
            {
                row[x] = color;
            }
        }
    }
}

/* 16 px ASCII 字库（板级定义在 lcdfont.h / lcd.c，这里只声明，不重复定义） */
extern const unsigned char asc2_1608[95][16];

static void ov_text_scaled(raster_surface_t *s, float inv, int x, int y,
                           const char *str, uint16_t color)
{
    int n = (inv > 1.5f) ? 2 : 1;

    for (const char *p = str; (*p != 0) && (*p != '\\n'); p++)
    {
        unsigned char c = (unsigned char)(*p);

        if ((c < ' ') || (c > '~'))
        {
            c = ' ';
        }

        const unsigned char *font = asc2_1608[c - ' '];

        for (int col = 0; col < 8; col++)
        {
            for (int row = 0; row < 16; row++)
            {
                int bit = col * 16 + row;
                int byteIdx = bit >> 3;
                int bitIdx = 7 - (bit & 7);

                if ((font[byteIdx] & (1u << bitIdx)) == 0u)
                {
                    continue;
                }

                int px = x + col;
                int py = y + row;
                int sx = (int)((float)px * inv);
                int sy = (int)((float)py * inv);

                ov_block(s, sx, sy, n, color);
            }
        }

        x += 8;
    }
}

/* 把一次覆盖层操作并入本帧脏矩形 */
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
}

void spine_overlay_rect(int x0, int y0, int x1, int y1, uint16_t color565)
{
    if ((g_ov_count >= SPINE_OV_MAX) || (!g_d.inited))
    {
        return;
    }

    if (x0 > x1) { int t = x0; x0 = x1; x1 = t; }
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }

    spine_ov_op_t *op = &g_ov[g_ov_count++];

    op->type = 0;
    op->x0 = (int16_t)x0;
    op->y0 = (int16_t)y0;
    op->x1 = (int16_t)x1;
    op->y1 = (int16_t)y1;
    op->thick = 0;
    op->color = color565;

    ov_extend_bbox(x0, y0, x1, y1);
}

void spine_overlay_frame(int x0, int y0, int x1, int y1, int thick, uint16_t color565)
{
    if ((g_ov_count >= SPINE_OV_MAX) || (!g_d.inited))
    {
        return;
    }

    if (x0 > x1) { int t = x0; x0 = x1; x1 = t; }
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }
    if (thick < 1) { thick = 1; }

    spine_ov_op_t *op = &g_ov[g_ov_count++];

    op->type = 1;
    op->x0 = (int16_t)x0;
    op->y0 = (int16_t)y0;
    op->x1 = (int16_t)x1;
    op->y1 = (int16_t)y1;
    op->thick = (int16_t)thick;
    op->color = color565;

    ov_extend_bbox(x0, y0, x1, y1);
}

void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565)
{
    if ((ascii == nullptr) || (g_ov_count >= SPINE_OV_MAX) || (!g_d.inited))
    {
        return;
    }

    spine_ov_op_t *op = &g_ov[g_ov_count++];
    int i = 0;

    op->type = 2;
    op->x0 = (int16_t)x;
    op->y0 = (int16_t)y;
    op->thick = 0;
    op->color = color565;

    for (; (ascii[i] != 0) && (i < (SPINE_OV_TEXT_MAX - 1)); i++)
    {
        op->text[i] = ascii[i];
    }
    op->text[i] = 0;

    op->x1 = (int16_t)(x + i * 8);
    op->y1 = (int16_t)(y + 16);

    ov_extend_bbox(x, y, op->x1, op->y1);
}

/* 由 spine_draw_end() 在实例绘制之后调用 */
static void spine_overlay_flush(raster_surface_t *s, float inv)
{
    for (int i = 0; i < g_ov_count; i++)
    {
        spine_ov_op_t *op = &g_ov[i];

        switch (op->type)
        {
            case 0:
                ov_rect_scaled(s, inv, op->x0, op->y0, op->x1, op->y1, op->color);
                break;

            case 1:
            {
                int t = op->thick;

                ov_rect_scaled(s, inv, op->x0, op->y0, op->x1, op->y0 + t - 1, op->color);
                ov_rect_scaled(s, inv, op->x0, op->y1 - t + 1, op->x1, op->y1, op->color);
                ov_rect_scaled(s, inv, op->x0, op->y0, op->x0 + t - 1, op->y1, op->color);
                ov_rect_scaled(s, inv, op->x1 - t + 1, op->y0, op->x1, op->y1, op->color);
                break;
            }

            case 2:
                ov_text_scaled(s, inv, op->x0, op->y0, op->text, op->color);
                break;

            default:
                break;
        }
    }

    g_ov_count = 0;
}
'''


def main():
    h = io.open(H, encoding="utf-8").read()

    if "spine_overlay_rect" in h:
        print("header: already patched")
    else:
        h = h.replace("/** 已注册实例数（诊断用；实例创建时自动注册，销毁时自动注销） */",
                      H_ADD.strip() + "\n\n/** 已注册实例数（诊断用；实例创建时自动注册，销毁时自动注销） */")
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: overlay API added")

    s = io.open(CPP, encoding="utf-8").read()

    if "spine_overlay_flush" in s:
        print("cpp: already patched")
        return

    # 1) 实现块插到"世界重力"之前
    anchor = "/*----------------------------------------------------------------- 世界重力 */"
    if anchor not in s:
        raise SystemExit("gravity anchor not found")
    s = s.replace(anchor, CPP_ADD.strip() + "\n\n" + anchor, 1)

    # 2) draw_begin 里清空覆盖层队列
    s = s.replace("""    g_d.qcount = 0;
    g_d.have_bbox = 0;""",
"""    g_d.qcount = 0;
    g_ov_count = 0;
    g_d.have_bbox = 0;""")

    # 3) draw_end 里、实例之后、present 之前 flush
    old = """    uint16_t *dst = g_d.bufs[idx];

    if (g_d.divisor == 1)"""
    new = """    /* 覆盖层画在实例之上 */
    spine_overlay_flush(&g_d.surf, (g_d.divisor == 1) ? 1.0f : 0.5f);

    uint16_t *dst = g_d.bufs[idx];

    if (g_d.divisor == 1)"""
    assert old in s
    s = s.replace(old, new, 1)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("cpp: overlay implemented and wired into draw_end")


if __name__ == "__main__":
    main()
