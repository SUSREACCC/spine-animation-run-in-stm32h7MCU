#!/usr/bin/env python3
"""Rewire spine_demo's HUD from the board LCD functions to the new overlay API.

The overlay API draws into the same render target as the spine layer, so:
  * no DMA2D / cache mismatch
  * no global background-colour surprise
  * works at any divisor (screen-pixel coordinates, expanded per pixel)

The HUD is now queued every frame between spine_draw_begin() and
spine_draw_end(), so it is redrawn with the frame and rides the dirty rect.

Run from the project root:  python DSH/middleware/patch_demo_overlay.py
"""
import io
import re

P = "User/spine_demo.c"

NEW_HUD = r'''/*----------------------------------------------------------------- HUD */

/* 覆盖层：走 spine_overlay_*，与 spine 层同一渲染目标。
 * 每帧在 spine_draw_begin() 与 spine_draw_end() 之间排队。 */
#define DEMO_SCENES   6

static char     s_hud_top[64];
static char     s_hud_bot[64];
static int      s_scene_now = 0;
static float    s_fps_now = 0.0f;
static float    s_prog_now = 0.0f;

static void demo_hud_queue(void)
{
    /* ---- 顶栏：6 个场景指示格 + 帧率条 + 场景名 ---- */
    spine_overlay_rect(0, 0, DEMO_W - 1, DEMO_HUD_TOP - 1, 0x0000);

    for (int k = 0; k < DEMO_SCENES; k++)
    {
        int cx = 8 + k * 26;

        spine_overlay_rect(cx, 5, cx + 20, 18,
                           (k == s_scene_now) ? (uint16_t)0xF800 : (uint16_t)0x2104);
    }

    {
        int w = (int)(s_fps_now * 4.0f);

        if (w > 292) { w = 292; }
        if (w < 0)   { w = 0; }

        spine_overlay_rect(486, 8, 778, 16, 0x18E3);
        spine_overlay_rect(486, 8, 486 + w, 16, 0x07E0);
    }

    /* ---- 底栏：进度条 + 统计信息 ---- */
    spine_overlay_rect(0, DEMO_H - DEMO_HUD_BOT, DEMO_W - 1, DEMO_H - 1, 0x0000);

    {
        int w = (int)(s_prog_now * (float)(DEMO_W - 8));

        if (w > DEMO_W - 8) { w = DEMO_W - 8; }
        if (w < 0)          { w = 0; }

        spine_overlay_rect(4, DEMO_H - 5, 4 + w, DEMO_H - 2, 0x001F);
    }

    spine_overlay_text(8, 4, s_hud_top, 0xFFFF);
    spine_overlay_text(8, DEMO_H - DEMO_HUD_BOT + 3, s_hud_bot, 0x07FF);
}

static void demo_hud_set(const char *top, const char *bot)
{
    if (top != 0)
    {
        strncpy(s_hud_top, top, sizeof(s_hud_top) - 1);
        s_hud_top[sizeof(s_hud_top) - 1] = 0;
    }

    if (bot != 0)
    {
        strncpy(s_hud_bot, bot, sizeof(s_hud_bot) - 1);
        s_hud_bot[sizeof(s_hud_bot) - 1] = 0;
    }

    printf("[DEMO] %s | %s\r\n", s_hud_top, s_hud_bot);
}

'''


def main():
    s = io.open(P, encoding="utf-8").read()

    # 1) 整段替换 HUD 实现
    a = s.find("/*----------------------------------------------------------------- HUD")
    b = s.find("/*----------------------------------------------------------------- 场景公共")
    if a < 0 or b < 0:
        raise SystemExit("HUD section markers not found")

    s = s[:a] + NEW_HUD + s[b:]

    # 2) 帧循环里排队 HUD：在实例绘制之后、draw_end 之前
    old = """        spine_draw_begin(divisor);

        for (int i = 0; i < n; i++)
        {
            if (list[i] != 0)
            {
                spine_instance_draw(list[i]);
            }
        }

        spine_draw_end();"""
    new = """        spine_draw_begin(divisor);

        for (int i = 0; i < n; i++)
        {
            if (list[i] != 0)
            {
                spine_instance_draw(list[i]);
            }
        }

        demo_hud_queue();           /* 覆盖层：与实例同一帧、同一渲染目标 */
        spine_draw_end();"""
    if old not in s:
        raise SystemExit("draw loop pattern not found")
    s = s.replace(old, new, 1)

    # 3) 每 30 帧更新 fbs/progress 与文本（不再直接画）
    old2 = re.search(
        r"        /\* 每半秒重刷 HUD.*?\n        \}\n", s, re.S)
    if old2:
        s = s[:old2.start()] + """        /* 每 30 帧更新一次 HUD 内容（绘制由 demo_hud_queue 每帧完成） */
        if ((f % 30) == 0)
        {
            uint32_t el = plat_now_ms() - t0;
            char buf[64];

            s_fps_now = (el > 0) ? (1000.0f * (float)(f + 1) / (float)el) : 0.0f;
            s_prog_now = (float)(f + 1) / (float)frames;

            snprintf(buf, sizeof(buf), "%s %.1fFPS %dINST",
                     (divisor == 1) ? "800X480" : "HALF", (double)s_fps_now, n);
            demo_hud_set(0, buf);
        }
""" + s[old2.end():]

    # 4) 主入口最后一次 flush 改成队列 + 空帧渲染（不再直接刷屏）
    s = s.replace("""    demo_hud_flush();

    for (;;)""", """    for (;;)""")

    # 5) 末尾提示
    s = s.replace('        demo_hud_set("=== 循环演示结束，重新开始 ===", "restart in 2s");',
                  '        demo_hud_set("=== LOOP END / RESTART ===", "2S");')

    # 6) 去掉不再使用的 include（lcd/ltdc/delay）
    s = s.replace('#include "./BSP/LCD/lcd.h"\n#include "./BSP/LCD/ltdc.h"\n#include "./SYSTEM/delay/delay.h"\n', "")

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("spine_demo rewired to the overlay API")


if __name__ == "__main__":
    main()
