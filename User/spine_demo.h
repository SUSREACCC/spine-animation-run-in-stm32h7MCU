/**
 ****************************************************************************************************
 * @file        spine_demo.h
 * @brief       Spine 运行时功能展示入口
 ****************************************************************************************************
 */

#ifndef __SPINE_DEMO_H
#define __SPINE_DEMO_H

/* 1 = 自检跑完后进入循环展示；0 = 只跑自检并打印心跳 */
#ifndef SPINE_RUN_DEMO
#define SPINE_RUN_DEMO    1
#endif

#ifdef __cplusplus
extern "C" {
#endif

/** 循环演示所有已实现功能（不返回） */
void spine_demo_run(void);

#ifdef __cplusplus
}
#endif

#endif
