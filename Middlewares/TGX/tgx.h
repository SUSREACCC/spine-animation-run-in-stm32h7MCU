/**
 ****************************************************************************************************
 * @file        tgx.h
 * @brief       TGX 2D 子集入口（本项目裁剪版）
 * @note        原始库：thirdPartyComponents/tgx-main（版权见各文件头部）
 *
 *  裁剪说明（只保留 Spine 2D 渲染所需）：
 *    - 保留：Misc / Vec2 / Vec3 / Vec4 / Box2 / Color / Fonts / ShaderParams / Shaders /
 *            Rasterizer / bseg / Image（含 .inl 与 Color.cpp / Fonts.cpp）
 *    - 去掉：Mat4、Box3、Mesh3D、Mesh3Dv2、Renderer3D（3D 管线，Spine 用不到）
 *    - 去掉：font_tgx_*.cpp/h（约 4.3 MB 内置字库数据，本项目用 LCD 字库）
 ****************************************************************************************************
 */

#ifndef TGX_TRIMMED_H
#define TGX_TRIMMED_H

/* 必须最先包含：AC6 的 libcxx <math.h> 引入 abs(float/double) 重载后，
 * TGX 中的 abs(int) 调用会二义；先引入 <stdlib.h> 让 int 版本可见。 */
/* 点采样开关：实测双线性约 176 cycles/px，点采样可显著降低 */
#ifndef TGX_TEXTURE_POINT
#define TGX_TEXTURE_POINT 1
#endif

#include <stdlib.h>

#include "Misc.h"
#include "Vec2.h"
#include "Vec3.h"
#include "Vec4.h"
#include "Box2.h"
#include "Color.h"
#include "Fonts.h"
#include "Image.h"

#endif /* TGX_TRIMMED_H */
