/**
 ****************************************************************************************************
 * @file        tgx_selftest.h
 * @brief       TGX 2D 渲染自检 + 吞吐基准（C 接口，供 selftest.c 调用）
 ****************************************************************************************************
 */

#ifndef __TGX_SELFTEST_H
#define __TGX_SELFTEST_H

#include "./SYSTEM/sys/sys.h"

#ifdef __cplusplus
extern "C" {
#endif

/* 返回 0 表示通过 */
uint8_t tgx_selftest(void);

#ifdef __cplusplus
}
#endif

#endif
