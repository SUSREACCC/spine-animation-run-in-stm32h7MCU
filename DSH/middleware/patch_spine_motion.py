#!/usr/bin/env python3
"""Append a motion check to spine_anim_sheet: render the same clip at two
different times into the same cell and compare the cell checksums.  A non-zero
difference proves the animation is actually evaluated over time (not just a
static setup pose).

Run from the project root:  python DSH/middleware/patch_spine_motion.py
"""
import io

PATH = "User/spine_test.cpp"

BLOCK = r'''
    /* ---- 运动校验：同一 clip 两个时间点，比较单元格校验和 ---- */
    {
        size_t idx = 7;                     /* "run" */

        if (idx < n_anim)
        {
            int cx = (int)(idx % cols);
            int cy = (int)(idx / cols);
            float ox = cx * cell_w + (cell_w - (wmaxx - wminx) * cell_scale) * 0.5f - wminx * cell_scale;
            float oy = cy * cell_h + 14.0f - wminy * cell_scale;

            uint32_t sums[2];

            for (int k = 0; k < 2; k++)
            {
                skeleton.setupPose();
                state.clearTracks();
                state.setAnimation(0, sd->getAnimations()[idx]->getName(), true);
                state.update((k == 0) ? at_time : (at_time + 0.30f));
                state.apply(skeleton);
                skeleton.updateWorldTransform(spine::Physics_Update);

                /* 只清这个单元格 */
                for (int yy = cy * (int)cell_h; yy < (cy + 1) * (int)cell_h; yy++)
                {
                    uint16_t *row = s_surf.px + (size_t)yy * s_surf.stride;

                    for (int xx = cx * (int)cell_w; xx < (cx + 1) * (int)cell_w; xx++)
                    {
                        row[xx] = 0x1082u;
                    }
                }

                draw_commands(renderer.render(skeleton), cell_scale, ox, oy);

                uint32_t sum = 0;

                for (int yy = cy * (int)cell_h; yy < (cy + 1) * (int)cell_h; yy++)
                {
                    const uint16_t *row = s_surf.px + (size_t)yy * s_surf.stride;

                    for (int xx = cx * (int)cell_w; xx < (cx + 1) * (int)cell_w; xx += 3)
                    {
                        sum = sum * 31u + row[xx];
                    }
                }

                sums[k] = sum;
            }

            /* 恢复 t0 的姿势，保证总览图仍是原样 */
            skeleton.setupPose();
            state.clearTracks();
            state.setAnimation(0, sd->getAnimations()[idx]->getName(), true);
            state.update(at_time);
            state.apply(skeleton);
            skeleton.updateWorldTransform(spine::Physics_Update);
            draw_commands(renderer.render(skeleton), cell_scale, ox, oy);

            printf("[SPN] motion check (%s): t0=%08lX t1=%08lX %s\r\n",
                   sd->getAnimations()[idx]->getName().buffer(),
                   (unsigned long)sums[0], (unsigned long)sums[1],
                   (sums[0] != sums[1]) ? "MOVING" : "STATIC (bad)");
        }
    }

'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "motion check" in s:
        print("motion check already present")
        return

    anchor = "    raster_flush((uint16_t *)FB_ADDR, SCR_W * SCR_H * 2);\n\n    float ms = (float)cycles / 480000.0f;"

    if anchor not in s:
        print("anchor not found")
        return

    s = s.replace(anchor, BLOCK + anchor, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("motion check inserted")


if __name__ == "__main__":
    main()
