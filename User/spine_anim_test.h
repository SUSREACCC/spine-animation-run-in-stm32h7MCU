/**
 ****************************************************************************************************
 * @file        spine_anim_test.h
 * @brief       动画衔接测试
 ****************************************************************************************************
 */

#ifndef __SPINE_ANIM_TEST_H
#define __SPINE_ANIM_TEST_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 验证动画衔接：默认过渡、当前动画名、进度接回、排队下一段。
 * @param frames 每阶段跑多少帧
 * @return 1 = PASS，0 = FAIL
 */
int spine_anim_test(const char *skel_path, const char *atlas_path, int frames);

#ifdef __cplusplus
}
#endif

#endif
