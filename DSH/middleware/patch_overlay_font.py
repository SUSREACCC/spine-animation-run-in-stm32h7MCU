#!/usr/bin/env python3
"""Overlay text: switch from the board font to the bundled 5x7 font.

The board font (asc2_1608) came out transposed/garbled when read from our
module, so the overlay now uses spine_font.h, generated and eyeballed by
DSH/middleware/gen_font.py.

Scale 2 by default (10x14 px, 12 px advance) so the HUD is readable on 480p.
Also adds spine_overlay_text_s(x, y, str, color, scale).

Run from the project root:  python DSH/middleware/patch_overlay_font.py
"""
import io

CPP = "User/spine_api.cpp"
H = "User/spine_api.h"

OLD_TEXT = r'''/* 16 px ASCII 字库（板级定义在 lcdfont.h / lcd.c，这里只声明，不重复定义） */
extern const unsigned char asc2_1608[95][16];

static void ov_text_scaled(raster_surface_t *s, float inv, int x, int y,
                           const char *str, uint16_t color)
{
    int n = (inv > 1.5f) ? 2 : 1;

    for (const char *p = str; (*p != 0) && (*p != '\n'); p++)
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
}'''

NEW_TEXT = r'''/* 自带 5x7 字库（生成文件，见 gen_font.py），不依赖板级字模 */
#include "spine_font.h"

/**
 * 渲染一段 ASCII 文本。
 * @param x,y   屏幕像素左上角
 * @param scale 放大倍数（1 => 5x7，2 => 10x14，字符步进 (5+1)*scale）
 */
static void ov_text_at(raster_surface_t *s, int x, int y,
                       const char *str, uint16_t color, int scale)
{
    if (scale < 1)
    {
        scale = 1;
    }

    int step = (SPINE_FONT_W + 1) * scale;

    for (const char *p = str; (*p != 0) && (*p != '\n'); p++)
    {
        unsigned char c = (unsigned char)(*p);
        int idx = (int)c - SPINE_FONT_FIRST;

        if (idx < 0 || idx > (SPINE_FONT_LAST - SPINE_FONT_FIRST))
        {
            idx = 0;                        /* 未知字符 -> 空格 */
        }

        const uint8_t *g = g_spine_font[idx];

        for (int col = 0; col < SPINE_FONT_W; col++)
        {
            uint8_t bits = g[col];

            for (int row = 0; row < SPINE_FONT_H; row++)
            {
                if (((bits >> row) & 1u) == 0u)
                {
                    continue;
                }

                int bx = x + col * scale;
                int by = y + row * scale;

                for (int dy = 0; dy < scale; dy++)
                {
                    for (int dx = 0; dx < scale; dx++)
                    {
                        ov_block(s, bx + dx, by + dy, 1, color);
                    }
                }
            }
        }

        x += step;
    }
}'''


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "g_spine_font" in s:
        print("already using the bundled font")
    else:
        assert OLD_TEXT in s, "board-font block not found"
        s = s.replace(OLD_TEXT, NEW_TEXT, 1)

        # flush 里的调用改成新函数（默认 2 倍）
        old_call = """            case 2:
                ov_text_scaled(s, inv, op->x0, op->y0, op->text, op->color);
                break;"""
        new_call = """            case 2:
                ov_text_at(s, op->x0, op->y0, op->text, op->color, op->thick > 0 ? op->thick : 2);
                break;"""
        assert old_call in s
        s = s.replace(old_call, new_call, 1)

        # 文本 op 的 bbox：按 5x7 + 步进 12（scale 2）估算
        old_bbox = """    op->x1 = (int16_t)(x + i * 8);
    op->y1 = (int16_t)(y + 16);"""
        new_bbox = """    op->x1 = (int16_t)(x + i * 12 + 2);
    op->y1 = (int16_t)(y + 14);"""
        assert old_bbox in s
        s = s.replace(old_bbox, new_bbox, 1)

        io.open(CPP, "w", encoding="utf-8", newline="").write(s)
        print("overlay text switched to the bundled 5x7 font (scale 2)")

    # 头文件：补一个可指定 scale 的版本
    h = io.open(H, encoding="utf-8").read()
    if "spine_overlay_text_s" not in h:
        h = h.replace("/** 16 px 高 ASCII 文本（复用板级 asc2_1608 字库） */\nvoid spine_overlay_text(int x, int y, const char *ascii, uint16_t color565);",
"""/** ASCII 文本（自带 5x7 字库，默认 scale=2 即 10x14 像素） */
void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565);

/** 同上，可指定放大倍数（1..4） */
void spine_overlay_text_s(int x, int y, const char *ascii, uint16_t color565, int scale);""")
        io.open(H, "w", encoding="utf-8", newline="").write(h)

        s = io.open(CPP, encoding="utf-8").read()
        if "void spine_overlay_text_s(" not in s:
            s = s.replace("""void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565)
{""",
"""void spine_overlay_text_s(int x, int y, const char *ascii, uint16_t color565, int scale)
{
    spine_overlay_text(x, y, ascii, color565);

    if ((g_ov_count > 0) && (scale > 0) && (scale != 2))
    {
        g_ov[g_ov_count - 1].thick = (int16_t)scale;
    }
}

void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565)
{""", 1)
            io.open(CPP, "w", encoding="utf-8", newline="").write(s)
            print("spine_overlay_text_s added")


if __name__ == "__main__":
    main()
