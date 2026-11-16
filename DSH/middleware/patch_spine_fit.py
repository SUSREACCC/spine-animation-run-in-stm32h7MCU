#!/usr/bin/env python3
"""Rewrite the transform part of User/spine_test.cpp so the skeleton is fitted
into the screen from its measured world-space bounding box (two pass).

Line based patching: replaces the block that computes scale/ox/oy and the frame
loop header with a version that measures first.

Run from the project root:  python DSH/middleware/patch_spine_fit.py
"""
import io

PATH = "User/spine_test.cpp"

OLD_START = "    float scale = (sd->getHeight() > 1.0f)"
OLD_END = "    /* ---- 帧循环 ---- */"


def main():
    src = io.open(PATH, encoding="utf-8").read()
    lines = src.split("\n")

    try:
        i0 = next(i for i, ln in enumerate(lines) if ln.startswith(OLD_START))
        i1 = next(i for i, ln in enumerate(lines) if ln.startswith(OLD_END))
    except StopIteration:
        print("anchor not found")
        return

    new_block = [
        "    /* ---- 第一遍：测世界包围盒，自动缩放到屏幕 ---- */",
        "    skeleton.setupPose();",
        "    skeleton.updateWorldTransform(spine::Physics_Update);",
        "    state.apply(skeleton);",
        "    skeleton.updateWorldTransform(spine::Physics_Update);",
        "",
        "    float wminx = 1e9f, wmaxx = -1e9f, wminy = 1e9f, wmaxy = -1e9f;",
        "    {",
        "        spine::RenderCommand *m = renderer.render(skeleton);",
        "",
        "        while (m != nullptr)",
        "        {",
        "            for (int i = 0; i < m->numVertices; i++)",
        "            {",
        "                float x = m->positions[2 * i + 0];",
        "                float y = m->positions[2 * i + 1];",
        "",
        "                if (x < wminx) { wminx = x; }",
        "                if (x > wmaxx) { wmaxx = x; }",
        "                if (y < wminy) { wminy = y; }",
        "                if (y > wmaxy) { wmaxy = y; }",
        "            }",
        "            m = m->next;",
        "        }",
        "    }",
        "",
        "    if ((wmaxx <= wminx) || (wmaxy <= wminy))",
        "    {",
        "        printf(\"[SPN] empty skeleton bounds\\r\\n\");",
        "        return 5;",
        "    }",
        "",
        "    const float margin_top = 30.0f;",
        "    const float margin_bot = 30.0f;",
        "    const float margin_x = 40.0f;",
        "",
        "    float sx = (SCR_W - 2 * margin_x) / (wmaxx - wminx);",
        "    float sy = (SCR_H - margin_top - margin_bot) / (wmaxy - wminy);",
        "    float scale = (sx < sy) ? sx : sy;",
        "",
        "    /* 屏幕 y 向下：y' = SCR_H - (y * scale + oy) */",
        "    float ox = (SCR_W - (wminx + wmaxx) * scale) * 0.5f;",
        "    float oy = SCR_H - margin_top - wmaxy * scale;",
        "",
        "    printf(\"[SPN] fit: world=(%.0f,%.0f)-(%.0f,%.0f) scale=%.3f ox=%.0f oy=%.0f\\r\\n\",",
        "           wminx, wminy, wmaxx, wmaxy, scale, ox, oy);",
        "",
    ]

    lines = lines[:i0] + new_block + lines[i1:]
    io.open(PATH, "w", encoding="utf-8", newline="").write("\n".join(lines))
    print("fit block installed (lines %d..%d replaced)" % (i0, i1))


if __name__ == "__main__":
    main()
