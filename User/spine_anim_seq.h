/**
 ****************************************************************************************************
 * @file        spine_anim_seq.h
 * @brief       动画序列测试：walk -> idle -> aim(触摸驱动 aim-ik) -> death(单次)
 ****************************************************************************************************
 */

#ifndef __SPINE_ANIM_SEQ_H
#define __SPINE_ANIM_SEQ_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 按脚本播放 4 段动画，aim 段允许触摸驱动 aim-ik。
 *
 *  walk  5 s（循环）
 *  idle  5 s（循环）
 *  aim  10 s（循环，触摸驱动 aim-ik）
 *  death 5 s（**单次**，不循环）
 *
 * @return 1 = 全部阶段跑完，0 = 加载失败
 */
int spine_anim_seq(const char *skel_path, const char *atlas_path);

#ifdef __cplusplus
}
#endif

#endif
