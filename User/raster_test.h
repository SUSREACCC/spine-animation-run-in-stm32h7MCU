/**
 ****************************************************************************************************
 * @file        raster_test.h
 * @brief       自写光栅器回归 + 基准入口（C 接口）
 ****************************************************************************************************
 */

#ifndef __RASTER_TEST_H
#define __RASTER_TEST_H

#include "./SYSTEM/sys/sys.h"

#ifdef __cplusplus
extern "C" {
#endif

extern float g_r2d_mpx;

/* 返回 0 表示全部回归项通过 */
uint8_t raster_test(void);

#ifdef __cplusplus
}
#endif

#endif
