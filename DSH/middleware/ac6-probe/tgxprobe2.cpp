// TGX 纹理三角形探针 —— 覆盖 Spine 渲染命令所需的关键路径：
//   纹理 + UV + 每顶点颜色(渐变/alpha) + 双线性采样 + 混合
// 编译: armclang --target=arm-arm-none-eabi -mcpu=cortex-m7 -mfpu=fpv5-d16 \
//        -mfloat-abi=hard -std=c++1z -O2 -include fix_stdlib.h -I <tgx>/src -c tgxprobe2.cpp
// 实测: 0 error, 代码 3,288 B (-O2)

#include "tgx.h"
#include <stdint.h>

using namespace tgx;

extern "C" void spine_draw_tris(RGB565 *fb, int fw, int fh,
                                RGB565 *tex, int tw, int th,
                                const float *xy, const float *uv,
                                const RGB565 *cols, int ntri)
{
    Image<RGB565> dst(fb, fw, fh);
    Image<RGB565> src(tex, tw, th);

    for (int i = 0; i < ntri; i++) {
        const float *p = xy + i * 6;
        const float *t = uv + i * 6;
        dst.drawTexturedGradientTriangle(src,
                fVec2(t[0], t[1]), fVec2(t[2], t[3]), fVec2(t[4], t[5]),
                fVec2(p[0], p[1]), fVec2(p[2], p[3]), fVec2(p[4], p[5]),
                cols[i * 3], cols[i * 3 + 1], cols[i * 3 + 2]);
    }
}
