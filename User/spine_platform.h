/**
 ****************************************************************************************************
 * @file        spine_platform.h
 * @brief       spine-cpp 平台层：SDRAM 分配器 + （后续）FatFs 流 / 纹理加载
 * @note        内存布局（SDRAM 32 MB）：
 *                0xC0000000 + 2 MB  : LTDC 帧缓冲（1280x800 RGB565）
 *                0xC0200000 + 8 MB  : spine 堆（自定义 first-fit 分配器）
 *                0xC0A00000 + 16 MB : 纹理/资源区
 ****************************************************************************************************
 */

#ifndef __SPINE_PLATFORM_H
#define __SPINE_PLATFORM_H

#include "./SYSTEM/sys/sys.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SPINE_HEAP_BASE     0xC0200000u
#define SPINE_HEAP_SIZE     (8u * 1024u * 1024u)

#define SPINE_ARENA_BASE    0xC0A00000u
#define SPINE_ARENA_SIZE    (16u * 1024u * 1024u)

/* 分配器使用统计，便于在自检里打印 */
typedef struct
{
    uint32_t used_bytes;
    uint32_t peak_bytes;
    uint32_t alloc_count;
    uint32_t fail_count;
} spine_heap_stats_t;

void spine_heap_get_stats(spine_heap_stats_t *st);

/* 分配器当前链表块数（用于诊断碎片化） */
uint32_t spine_heap_block_count(void);

#ifdef __cplusplus
}
#endif

#endif
