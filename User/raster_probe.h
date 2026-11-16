/**
 ****************************************************************************************************
 * @file        raster_probe.h
 * @brief       最小自写光栅器吞吐探针（C 接口）
 * @note        g_raster_mpx：最近一次测量得到的类 Spine 负载吞吐（Mpx/s）
 ****************************************************************************************************
 */

#ifndef __RASTER_PROBE_H
#define __RASTER_PROBE_H

#include "./SYSTEM/sys/sys.h"

#ifdef __cplusplus
extern "C" {
#endif

extern float g_raster_mpx;

/* 返回 0 表示通过 */
uint8_t raster_probe(void);

#ifdef __cplusplus
}
#endif

#endif
