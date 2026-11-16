/**
 ****************************************************************************************************
 * @file        raster2d.h
 * @brief       面向 Spine 的 2D 纹理三角形光栅器（RGB565 帧缓冲）
 * @note        设计要点：
 *                * 定点边界函数 + top-left 规则 → 相邻三角形无缝、无重复混合
 *                * 逐像素仅为 2 次浮点加法（UV 平面梯度），色调按需插值
 *                * 支持 3 种纹理格式：RGB565 色键 / ARGB1555 / ARGB4444
 *                * 4 种混合模式：Normal / Additive / Multiply / Screen
 *                * 任意顶点出屏（只按裁剪矩形光栅化，不会越界）
 *                * 无动态分配、无异常、无 RTTI
 *
 *  坐标约定：屏幕坐标，y 向下；UV 为纹理像素坐标。
 *  颜色约定：vertex.color 为 ARGB8888（直通 alpha，非预乘）。
 ****************************************************************************************************
 */

#ifndef __RASTER2D_H
#define __RASTER2D_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*------------------------------------------------------------------ 类型 */

typedef enum
{
    RASTER_FMT_RGB565 = 0,      /* 2 B/px，透明色由 key 指定（色键）      */
    RASTER_FMT_ARGB1555,        /* 2 B/px，1 bit alpha                    */
    RASTER_FMT_ARGB4444         /* 2 B/px，4 bit alpha（推荐给 Spine）    */
} raster_format_t;

typedef enum
{
    RASTER_BLEND_NORMAL = 0,    /* src over dst            */
    RASTER_BLEND_ADD,           /* dst + src               */
    RASTER_BLEND_MULTIPLY,      /* dst * src               */
    RASTER_BLEND_SCREEN        /* 1-(1-dst)*(1-src)       */
} raster_blend_t;

typedef struct
{
    uint16_t       *px;         /* 帧缓冲起始（RGB565）      */
    int             w;
    int             h;
    int             stride;     /* 行跨度，单位：像素        */
    int             clip_x0, clip_y0, clip_x1, clip_y1;   /* 含端点 */
} raster_surface_t;

typedef struct
{
    const uint16_t *px;
    int             w;
    int             h;
    int             stride;
    raster_format_t fmt;
    uint16_t        key;        /* 仅 RGB565：透明色（如 0x0000） */
} raster_texture_t;

typedef struct
{
    float    x, y;
    float    u, v;
    uint32_t color;             /* ARGB8888 逐顶点色调 */
} raster_vertex_t;

/*------------------------------------------------------------------ API */

/** 用一个顶点色/纹理填充整个裁剪区（用于清屏） */
void raster_clear(const raster_surface_t *s, uint16_t color565);

/** 画一个纹理三角形 */
void raster_triangle(const raster_surface_t *s, const raster_texture_t *t,
                     const raster_vertex_t *v0, const raster_vertex_t *v1,
                     const raster_vertex_t *v2, raster_blend_t blend, uint8_t opacity);

/** 画一条三角形带（Spine RenderCommand 的直接映射：verts + 索引） */
void raster_mesh(const raster_surface_t *s, const raster_texture_t *t,
                 const raster_vertex_t *verts, int nverts,
                 const uint16_t *indices, int nindices,
                 raster_blend_t blend, uint8_t opacity);

/** 把 SDRAM 帧缓冲的脏行写回（LTDC 扫描前必须调用） */
void raster_flush(uint16_t *fb, int bytes);

/**
 * 2 倍最近邻放大（半分辨率渲染用）：把 src 的矩形 [sx0..sx1] x [sy0..sy1]
 * 放大成 dst 中对应的 2 倍区域。矩形按像素包含端点。
 * 只放大脏矩形可以避免全屏放大把半分辨率的收益吃掉。
 */
void raster_upscale2x(const uint16_t *src, int src_stride,
                      uint16_t *dst, int dst_stride,
                      int sx0, int sy0, int sx1, int sy1);

#ifdef __cplusplus
}
#endif

#endif /* __RASTER2D_H */
