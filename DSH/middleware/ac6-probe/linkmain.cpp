// Spine C-API 集成驱动探针 —— 验证真实调用链可编译、可链接：
//   atlas 回调(lambda) -> skeleton_data_load_binary -> drawable -> render -> 遍历 RenderCommand
// 编译: 需要 spine-c/include、spine-cpp/include 与 TGX src 三个包含路径。

#include <stdint.h>
#include "tgx.h"
#include <spine-c.h>

using namespace tgx;

static RGB565 fb[480][800];

extern "C" void app(void)
{
    Image<RGB565> dst((RGB565 *)fb, 800, 480);
    dst.fillScreen(RGB565_Black);

    // 纹理加载回调：目标平台上映射为“从 QSPI/SDRAM 取 ARGB8888 图集页”
    spine_atlas_result ar = spine_atlas_load_callback(
        "", "",
        [](const char *) -> void * { return nullptr; },
        [](void *) {});

    spine_atlas atlas = spine_atlas_result_get_atlas(ar);

    // 骨架：推荐 .skel 二进制（比 JSON 省约 52 KB 代码与更多 RAM）
    const char *skel = "";
    spine_skeleton_data_result sr =
        spine_skeleton_data_load_binary(atlas, (const uint8_t *)skel, 0, "");
    spine_skeleton_data sd = spine_skeleton_data_result_get_data(sr);

    spine_skeleton_drawable d = spine_skeleton_drawable_create(sd);
    spine_skeleton_drawable_update(d, 0.016f);

    for (spine_render_command cmd = spine_skeleton_drawable_render(d);
         cmd != nullptr; cmd = spine_render_command_get_next(cmd)) {
        float    *pos = spine_render_command_get_positions(cmd);
        float    *uv  = spine_render_command_get_uvs(cmd);
        uint32_t *col = spine_render_command_get_colors(cmd);
        int       nv  = spine_render_command_get_num_vertices(cmd);
        int       ni  = spine_render_command_get_num_indices(cmd);
        int       bm  = (int)spine_render_command_get_blend_mode(cmd);
        void     *tex = spine_render_command_get_texture(cmd);

        (void)pos; (void)uv; (void)col; (void)nv; (void)ni; (void)bm; (void)tex;
        // 实际实现：按 indices 取 3 个顶点 -> drawTexturedGradientTriangle(...)
        // blendMode: NORMAL/ADDITIVE/MULTIPLY/SCREEN -> TGX 自定义 blend 算子
    }

    spine_skeleton_drawable_dispose(d);
}
