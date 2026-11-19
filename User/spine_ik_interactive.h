/**
 ****************************************************************************************************
 * @file        spine_ik_interactive.h
 * @brief       触摸交互：点击屏幕驱动 IK 目标
 ****************************************************************************************************
 */

#ifndef __SPINE_IK_INTERACTIVE_H
#define __SPINE_IK_INTERACTIVE_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 交互测试：把屏幕点击位置换算成骨架世界坐标，作为 IK 目标。
 *
 * @param skel_path   骨架路径
 * @param atlas_path  图集路径
 * @param ik_name     IK 约束名（如 "rear-leg-ik"）
 * @param max_seconds 最长运行秒数（到点返回）
 * @return 1 = 收到过触摸，-1 = 没触摸，0 = 失败
 */
int spine_ik_interactive(const char *skel_path, const char *atlas_path,
                         const char *ik_name, int max_seconds);

#ifdef __cplusplus
}
#endif

#endif
