/**
 ****************************************************************************************************
 * @file        spine_test.h
 * @brief       spine-cpp 集成测试入口
 ****************************************************************************************************
 */

#ifndef __SPINE_TEST_H
#define __SPINE_TEST_H

#include "./SYSTEM/sys/sys.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 返回 0 表示成功 */
uint8_t spine_test_run(const char *skel_path, const char *atlas_path, const char *anim, int frames);

/* 渲染所有动画的总览网格（一帧一图） */
uint8_t spine_anim_sheet(const char *skel_path, const char *atlas_path, float at_time);

/* 实时循环播放指定动画（双缓冲，framerate 由 fps 决定） */
/* divisor: 1=全分辨率, 2=半分辨率(渲染 1/4 像素后 2x 放大) */
uint8_t spine_play(const char *skel_path, const char *atlas_path, const char *anim, int fps, int seconds, int divisor);

/* 双角色（不同动画）+ 每次迭代重新从文件加载，用于负载与泄漏测试 */
void  fb_bench(void);
void  fb_mpu_set(int mode);


/* 物理重力演示：给骨骼注入物理约束并旋转重力方向 */
uint8_t spine_gravity_test(const char *skel_path, const char *atlas_path,
                           const char *anim, int fps, int seconds,
                           int divisor, const char *bone_name);

uint8_t spine_play_duo(const char *skel_path, const char *atlas_path,
                       const char *anim_a, const char *anim_b,
                       int fps, int seconds, int divisor, int iterations);

#ifdef __cplusplus
}
#endif

#endif
