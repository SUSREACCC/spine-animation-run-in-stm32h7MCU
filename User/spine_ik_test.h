/**
 ****************************************************************************************************
 * @file        spine_ik_test.h
 * @brief       IK 目标驱动测试（独立模块）
 ****************************************************************************************************
 */

#ifndef __SPINE_IK_TEST_H
#define __SPINE_IK_TEST_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 枚举素材里的 IK 约束，驱动其中一个的目标位置，并校验末端确实跟随。
 *
 * @param skel_path   骨架路径（如 "/spine/spineboy-pro.skel"）
 * @param atlas_path  图集路径
 * @param anim        播放的动画名（NULL = 不播放）
 * @param hold_frames 每个测试阶段跑多少帧
 * @param visual      1 = 最后再渲染几秒让效果可见
 * @return 1 = PASS，0 = FAIL，-1 = 素材没有 IK（跳过）
 */
int spine_ik_test(const char *skel_path, const char *atlas_path,
                  const char *anim, int hold_frames, int visual);

#ifdef __cplusplus
}
#endif

#endif
