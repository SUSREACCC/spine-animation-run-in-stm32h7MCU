/**
 ****************************************************************************************************
 * @file        spine_api.h
 * @brief       Spine 运行时对外 API（C 接口，供游戏代码 / GUI 框架调用）
 *
 * 设计原则：
 *   - 资产（骨架 + 图集 + 纹理）与实例（一个角色）分离，资产可被多个实例共享
 *   - 加载与播放分离：加载一次，之后每帧只做 update + draw
 *   - 绘制顺序 = 层级顺序（先画的在下）
 *   - 不阻塞、不自己跑循环，完全由调用者的主循环驱动
 *
 * 典型用法：
 *      spine_asset_t *a = spine_asset_load("/spine/hero.skel", "/spine/hero.atlas");
 *      spine_instance_t *hero = spine_instance_create(a);
 *      spine_instance_play(hero, "run", 1, 0);
 *      spine_instance_set_position(hero, 400, 240);
 *      spine_instance_set_scale(hero, 0.5f);
 *
 *      while (1) {
 *          float dt = frame_dt();
 *          spine_instance_update(hero, dt);
 *          spine_draw_begin(2);          // 2 = 半分辨率
 *          spine_instance_draw(hero);
 *          spine_draw_end();
 *      }
 ****************************************************************************************************
 */

#ifndef __SPINE_API_H
#define __SPINE_API_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*==================================================================================================
 * 类型
 *=================================================================================================*/

typedef struct spine_asset    spine_asset_t;      /* 共享资产：骨架数据 + 图集 + 纹理 */
typedef struct spine_instance spine_instance_t;   /* 一个角色实例 */

/*==================================================================================================
 * 资产：加载一次，可被多个实例共享
 *=================================================================================================*/

/**
 * 从 SD 卡加载骨架与图集（.skel + .atlas + 对应的 .raw 纹理）。
 * @param  skel_path   例 "/spine/hero.skel"
 * @param  atlas_path  例 "/spine/hero.atlas"
 * @return 非空成功；失败返回 0
 */
spine_asset_t *spine_asset_load(const char *skel_path, const char *atlas_path);

/** 释放资产（所有实例必须先销毁） */
void spine_asset_free(spine_asset_t *asset);

/** 动画数量 / 名称枚举（用于 UI 或调试） */
int         spine_asset_anim_count(spine_asset_t *asset);
const char *spine_asset_anim_name(spine_asset_t *asset, int index);

/** 该资产占用的纹理字节数（诊断用） */
uint32_t spine_asset_texture_bytes(spine_asset_t *asset);

/*==================================================================================================
 * 实例：一个角色
 *=================================================================================================*/

/** 创建实例（同一资产可创建多个，状态互相独立） */
spine_instance_t *spine_instance_create(spine_asset_t *asset);

/** 销毁实例 */
void spine_instance_destroy(spine_instance_t *in);

/*----------------------------------------------------------------- 动画 */

/**
 * 播放动画。
 * @param anim   动画名（NULL 或 "" = 停）
 * @param loop   1 = 循环
 * @param track  轨道号，0 = 基础层；多轨道可做上半身/下半身混合
 */
void spine_instance_play(spine_instance_t *in, const char *anim, int loop, int track);

/** 停止某条轨道 */
void spine_instance_stop(spine_instance_t *in, int track);

/** 设置某条轨道的播放速度（1.0 = 原速） */
void spine_instance_set_speed(spine_instance_t *in, float speed, int track);

/** 立刻跳到某条轨道的指定秒数 */
void spine_instance_set_time(spine_instance_t *in, float seconds, int track);

/*----------------------------------------------------------------- 变换与外观 */

/** 位置：骨架世界原点 (0,0) 在屏幕上的像素坐标 */
void spine_instance_set_position(spine_instance_t *in, float x, float y);

/** 缩放：世界单位 -> 屏幕像素（例 0.5 表示 1 世界单位 = 0.5 像素） */
void spine_instance_set_scale(spine_instance_t *in, float scale);

/** 水平/垂直翻转（1 = 翻转，0 = 正常） */
void spine_instance_set_flip(spine_instance_t *in, int flip_x, int flip_y);

/** 整体着色（RGBA8888，0xFFFFFFFF = 原色） */
void spine_instance_set_tint(spine_instance_t *in, uint32_t rgba8888);

/** 整体透明度（255 = 不透明） */
void spine_instance_set_alpha(spine_instance_t *in, uint8_t alpha);

/*----------------------------------------------------------------- 每帧 */

/**
 * 推进一帧：动画状态 -> 骨架姿态 -> 物理约束。
 * 必须每帧调用一次，物理（重力/惯性）才会生效。
 */
void spine_instance_update(spine_instance_t *in, float dt);

/**
 * 查询当前帧在屏幕上的包围盒（像素坐标）。
 * 未渲染过时会先算一次；无内容时返回 0。
 * @return 1 = 有效，0 = 空
 */
int spine_instance_get_bounds(spine_instance_t *in,
                              float *x0, float *y0, float *x1, float *y1);

/*==================================================================================================
 * 绘制：由调用者在主循环里驱动
 *=================================================================================================*/

/**
 * 开始一帧绘制。
 * @param divisor 1 = 全分辨率(800x480)，2 = 半分辨率(400x240 渲染后 2x 放大)
 *
 * 内部使用三缓冲 + 每缓冲脏矩形；分辨率变化时自动重建缓冲。
 */
void spine_draw_begin(int divisor);

/** 把一个实例追加到当前帧（调用顺序即层级，后画的盖在上面） */
void spine_instance_draw(spine_instance_t *in);

/** 结束一帧：清脏矩形 -> 光栅化 -> 放大 -> 切换缓冲 */
void spine_draw_end(void);

/** 当前帧已排队的实例数（诊断用） */
int spine_draw_queue_count(void);

/*==================================================================================================
 * 世界重力（影响所有物理约束）
 * 方向遵循 spine 约定：y 轴向下，(0,1)=向下，(0,-1)=向上
 *=================================================================================================*/

void  spine_world_set_gravity(float gx, float gy);
float spine_world_get_gravity_x(void);
float spine_world_get_gravity_y(void);

/** 已注册实例数（诊断用；实例创建时自动注册，销毁时自动注销） */
int spine_world_instance_count(void);

#ifdef __cplusplus
}
#endif

#endif /* __SPINE_API_H */
