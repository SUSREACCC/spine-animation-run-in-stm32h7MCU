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

/** 下一帧整屏重画（用于切场景 / 上电首帧，清掉上轮的残留像素） */
void spine_draw_force_full(void);

/** 当前帧已排队的实例数（诊断用） */
int spine_draw_queue_count(void);

/*==================================================================================================
 * 世界重力（影响所有物理约束）
 * 方向遵循 spine 约定：y 轴向下，(0,1)=向下，(0,-1)=向上
 *=================================================================================================*/

void  spine_world_set_gravity(float gx, float gy);
float spine_world_get_gravity_x(void);
float spine_world_get_gravity_y(void);

/*==================================================================================================
 * 覆盖层（HUD / UI / 调试）
 *
 * 与 spine 层画进同一块渲染目标，因此：
 *   - 跟随三缓冲，不会闪烁
 *   - 坐标用屏幕像素，半分辨率时自动按 divisor 展开（每个字形像素变成 divisor×divisor 块）
 *   - 会扩展脏矩形，保证被放大与清除
 *
 * 用法：spine_draw_begin() 之后、spine_draw_end() 之前调用（顺序无所谓，
 *       覆盖层总是画在所有 spine 实例之上）。
 *=================================================================================================*/

/** 实心矩形（屏幕像素，闭区间） */
void spine_overlay_rect(int x0, int y0, int x1, int y1, uint16_t color565);

/** 矩形边框 */
void spine_overlay_frame(int x0, int y0, int x1, int y1, int thick, uint16_t color565);

/** 16 px 高 ASCII 文本（复用板级 asc2_1608 字库） */
void spine_overlay_text(int x, int y, const char *ascii, uint16_t color565);

/** 本帧已排队的覆盖层操作数（诊断） */
int spine_overlay_count(void);

/*==================================================================================================
 * IK 约束（运行时驱动）
 *
 * 坐标一律是**骨架世界坐标**（spine 单位），不是屏幕像素。
 * 目标在下一帧的 update() 里生效（会先跑动画 apply，再写目标，最后解算 IK）。
 *=================================================================================================*/

/** IK 约束数量 */
int spine_instance_ik_count(spine_instance_t *in);

/** 第 index 个 IK 约束的名字（找不到返回 NULL） */
const char *spine_instance_ik_name(spine_instance_t *in, int index);

/** 该 IK 链有几根骨骼（通常 1 或 2） */
int spine_instance_ik_bone_count(spine_instance_t *in, const char *ik_name);

/** 设置 IK 目标位置（骨架世界坐标）。返回 1 = 成功 */
int spine_instance_set_ik_target(spine_instance_t *in, const char *ik_name,
                                 float world_x, float world_y);

/** 读取 IK 目标当前的世界坐标。返回 1 = 成功 */
int spine_instance_get_ik_target(spine_instance_t *in, const char *ik_name,
                                 float *world_x, float *world_y);

/** 读取 IK 链末端的实际世界坐标（用于判定 IK 是否真的跟随）。返回 1 = 成功 */
int spine_instance_get_ik_tip(spine_instance_t *in, const char *ik_name,
                              float *world_x, float *world_y);

/** 读取 IK 混入（0..1） */
float spine_instance_ik_mix(spine_instance_t *in, const char *ik_name);

/** 读取求解器实际使用的 mix（applied pose，诊断用） */
float spine_instance_ik_mix_applied(spine_instance_t *in, const char *ik_name);

/** 设置 IK 混入（0 = 关闭该约束，1 = 全量）。返回 1 = 成功 */
int spine_instance_set_ik_mix(spine_instance_t *in, const char *ik_name, float mix);

/** 清掉所有待应用的 IK 目标覆盖，并把目标骨骼还原到覆盖前的姿态
 *  （否则动画不驱动该骨骼时，偏移会永久保留，表现为运动范围整体平移） */
/**
 * 丢弃 IK 目标覆盖，但**保留目标骨骼当前姿态**（不还原）。
 *
 * 用途：配合"两段动画 + 过渡"的复位方案 ——
 *   按下 play(交互动画, 腿无时间轴) + set_ik_mix(1.0) + 每帧 set_ik_target
 *   松开 play(正常动画, mix) + release_ik_keep_pose()
 * 这样正常动画里目标骨骼的 timeline 会从"手指最后的位置"平滑过渡回正常目标，
 * 不需要运行时代码做插值。
 *
 * 与 spine_instance_clear_ik() 的区别：
 *   clear_ik()            还原目标骨骼到首次覆盖前的姿态（交互彻底结束时用）
 *   release_ik_keep_pose() 不还原，留给动画混合接管
 *
 * 注意：如果正常动画**不驱动**目标骨骼，目标会停在手指最后的位置，
 *       腿会一直偏向那里（这时应该用 clear_ik()）。
 */
void spine_instance_release_ik_keep_pose(spine_instance_t *in);

void spine_instance_clear_ik(spine_instance_t *in);

/*==================================================================================================
 * 动画衔接（过渡时长 / 排队 / 进度接回）
 *
 * 默认 defaultMix = 0，即 play() 切换动画是硬切；先 set_default_mix() 才有过渡。
 *=================================================================================================*/

/** 设置默认过渡时长（秒）。0 = 硬切 */
void spine_instance_set_default_mix(spine_instance_t *in, float seconds);

/** 设置 from -> to 的过渡时长（秒）。两个动画都要存在，否则返回 0 */
int spine_instance_set_mix(spine_instance_t *in, const char *from, const char *to, float seconds);


/** 读取动画总时长（秒）*/
float spine_instance_anim_duration(spine_instance_t *in, int track);

/** 读取实际动画时间（秒）：循环会在 [0,duration) 回绕，单次播放停在末尾 */
float spine_instance_anim_time(spine_instance_t *in, int track);

/** 读取当前播放进度（秒）*/
float spine_instance_get_time(spine_instance_t *in, int track);

/** 读取当前动画名；该轨没有动画时返回 NULL */
const char *spine_instance_current_anim(spine_instance_t *in, int track);

/** 跳到指定进度并保留时间缩放（切换动画后接回原进度用）。返回 1 = 成功 */
int spine_instance_seek(spine_instance_t *in, float seconds, int track);

/** 已注册实例数（诊断用；实例创建时自动注册，销毁时自动注销） */
int spine_world_instance_count(void);

#ifdef __cplusplus
}
#endif

#endif /* __SPINE_API_H */
