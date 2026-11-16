#!/usr/bin/env python3
"""Self-test demo for the normalised API (spine_api.h): two instances sharing one
asset, different animations, half-resolution, driven by an explicit frame loop.

Run from the project root:  python DSH/middleware/patch_api_demo.py
"""
import io

PATH = "User/selftest.c"

DEMO = r'''
/*----------------------------------------------------------------- 新 API 演示 */

static void api_demo(void)
{
    const char *SKEL = "/spine/celestial-circus-pro.skel";
    const char *ATLAS = "/spine/celestial-circus-pro.atlas";

    spine_asset_t *asset = spine_asset_load(SKEL, ATLAS);

    if (asset == 0)
    {
        printf("[API] asset load failed\r\n");
        return;
    }

    printf("[API] animations:");
    for (int i = 0; i < spine_asset_anim_count(asset); i++)
    {
        printf(" %s", spine_asset_anim_name(asset, i));
    }
    printf("\r\n[API] texture bytes: %lu\r\n", (unsigned long)spine_asset_texture_bytes(asset));

    spine_instance_t *hero = spine_instance_create(asset);
    spine_instance_t *enemy = spine_instance_create(asset);

    spine_instance_play(hero, "swing", 1, 0);
    spine_instance_play(enemy, "wing-flap", 1, 0);

    /* 用包围盒把两个角色摆到左右两侧，缩放到 220 px 高 */
    float x0 = 0, y0 = 0, x1 = 0, y1 = 0;

    if (spine_instance_get_bounds(hero, &x0, &y0, &x1, &y1) == 0)
    {
        printf("[API] bounds failed\r\n");
        return;
    }

    float h = y1 - y0;
    float s = (h > 1.0f) ? (220.0f / h) : 1.0f;
    float cx = (x0 + x1) * 0.5f;
    float cy = (y0 + y1) * 0.5f;

    spine_instance_set_scale(hero, s);
    spine_instance_set_position(hero, 210.0f - cx * s, 250.0f - cy * s);

    spine_instance_set_scale(enemy, s);
    spine_instance_set_position(enemy, 590.0f - cx * s, 250.0f - cy * s);
    spine_instance_set_tint(enemy, 0xFFB0D0FFu);       /* 轻微冷色调，验证 tint */

    printf("[API] bounds=(%.0f,%.0f)-(%.0f,%.0f) scale=%.3f\r\n",
           (double)x0, (double)y0, (double)x1, (double)y1, (double)s);

    const int   frames = 300;
    const float dt = 1.0f / 60.0f;
    uint32_t    t0 = HAL_GetTick();

    for (int f = 0; f < frames; f++)
    {
        spine_instance_update(hero, dt);
        spine_instance_update(enemy, dt);

        spine_draw_begin(2);                 /* 半分辨率 */
        spine_instance_draw(hero);
        spine_instance_draw(enemy);
        spine_draw_end();
    }

    float ms = (float)(HAL_GetTick() - t0) / (float)frames;

    printf("[API] %d frames | %.2f ms/frame (%.1f fps) | instances=%d queue=%d\r\n",
           frames, (double)ms, (double)(1000.0f / ms),
           spine_world_instance_count(), spine_draw_queue_count());

    spine_instance_destroy(hero);
    spine_instance_destroy(enemy);
    spine_asset_free(asset);

    printf("[API] after free: instances=%d\r\n", spine_world_instance_count());
    printf("[API] RESULT PASS\r\n");
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "api_demo" in s:
        print("api demo already present")
        return

    if '#include "spine_api.h"' not in s:
        s = s.replace('#include "spine_test.h"', '#include "spine_test.h"\n#include "spine_api.h"', 1)

    # 插入到 heartbeat 之前
    anchor = '    printf("heartbeat start\\r\\n");'
    if anchor not in s:
        raise SystemExit("heartbeat anchor not found")

    s = s.replace(anchor, DEMO.strip() + "\n\n" + anchor, 1)
    s = s.replace('    printf("heartbeat start', '    api_demo();\n\n    printf("heartbeat start', 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("api demo wired into self-test")


if __name__ == "__main__":
    main()
