/**
 ****************************************************************************************************
 * @file        plat.h
 * @brief       平台抽象层（PAL）：库与硬件之间唯一的耦合面
 *
 * 设计原则：
 *   1. 边界粗粒度 —— 每帧 / 每纹理调用，绝不出现在每像素循环里
 *   2. 不隐藏能力 —— 帧缓冲用"索引 + 指针"暴露，不要求拷贝
 *   3. 允许空实现 —— 无 D-Cache 的平台把 plat_cache_* 写成空函数即可
 *   4. 裸机 / RTOS 同源 —— 由 PLAT_USE_RTOS 切换，OS 原语是独立钩子
 *
 * 六组硬件接口：mem / fs / display / cache / time / log
 * 一组 OS 接口（仅 PLAT_USE_RTOS = 1 时需要实现）：sem / delay / tick / mem lock
 ****************************************************************************************************
 */

#ifndef __PLAT_H
#define __PLAT_H

#include <stdint.h>
#include <stddef.h>

#include "plat_cfg.h"

#ifdef __cplusplus
extern "C" {
#endif

/*==================================================================================================
 * 初始化
 *=================================================================================================*/

/**
 * 平台初始化：在 main 里、第一次绘制之前调用一次。
 * 裸机：空实现；RTOS：建立同步对象、打开 LTDC 重装中断。
 */
void plat_init(void);

/*==================================================================================================
 * 1. 内存
 *=================================================================================================*/

/**
 * 提供两段内存给运行时。库内部的分配器算法是可移植的，移植层只需交出内存。
 * @param heap        长期对象池（骨架、图集、实例、缓冲）
 * @param heap_size   字节数
 * @param arena       一次性资源区（纹理、顶点缓冲）
 * @param arena_size  字节数
 */
void plat_mem_pools(void **heap, size_t *heap_size, void **arena, size_t *arena_size);

/*==================================================================================================
 * 2. 文件系统
 *=================================================================================================*/

typedef struct plat_file plat_file_t;

/** 打开文件并返回句柄，成功返回 0（句柄由实现分配，最多同时 4 个） */
int  plat_file_open(plat_file_t **f, const char *path);
/** 读最多 bytes 字节，*got 返回实际读取量，成功返回 0 */
int  plat_file_read(plat_file_t *f, void *buf, size_t bytes, size_t *got);
/** 取文件大小，成功返回 0 */
int  plat_file_size(plat_file_t *f, size_t *bytes);
/** 关闭（允许 f 为空实现） */
void plat_file_close(plat_file_t *f);

/*==================================================================================================
 * 3. 显示
 *=================================================================================================*/

int   plat_display_w(void);
int   plat_display_h(void);

/** 帧缓冲数量（>= 2 才能双缓冲；当前 3） */
int   plat_fb_count(void);
/** 第 index 块帧缓冲的首地址（uint16_t*，格式 RGB565） */
void *plat_fb_addr(int index);

/**
 * 等上一帧的切换真正生效（裸机：轮询 VBR；RTOS：等信号量，让出 CPU）。
 * 单独暴露出来，方便调用者把等待放到合适的时机（例如动画计算之后）。
 */
void plat_fb_wait_ready(void);

/**
 * 把第 fb 块交给显示控制器。
 * PLAT_PRESENT_BLOCKING = 1 时会先调用 plat_fb_wait_ready() 再切换。
 */
void plat_fb_present(void *fb);

/**
 * 配置帧缓冲的缓存属性（平台相关，可选调用）：
 *   0 = write-back（默认），1 = non-cacheable，2 = write-through
 * 配成写穿后 plat_fb_need_cache_clean() 返回 0，可以省掉每帧的缓存冲刷。
 */
void plat_fb_set_cache_mode(int mode);

/* 帧缓冲是否仍需 CPU 手动写回缓存（配了写穿则为 0） */
int  plat_fb_need_cache_clean(void);

/*==================================================================================================
 * 4. 缓存
 *=================================================================================================*/

/** 写回：让显示控制器/DMA 能看到 CPU 刚写的数据 */
void plat_cache_clean(void *addr, size_t bytes);

/** 失效：丢弃缓存里可能过期的数据（DMA 写后 CPU 要读时用） */
void plat_cache_invalidate(void *addr, size_t bytes);

/*==================================================================================================
 * 5. 时间
 *=================================================================================================*/

uint32_t plat_now_ms(void);
uint64_t plat_now_us(void);
void     plat_delay_ms(uint32_t ms);

/*==================================================================================================
 * 6. 日志
 *=================================================================================================*/

void plat_log(const char *fmt, ...);

/*==================================================================================================
 * 7. OS 钩子（仅 PLAT_USE_RTOS = 1 时需要移植层实现）
 *
 *    裸机模式下这里全部是空实现，库代码可以无条件调用，不需要 #if。
 *=================================================================================================*/

#if PLAT_USE_RTOS

typedef void *plat_sem_t;

/** 创建二值信号量；ready != 0 表示创建后即可被 take 一次 */
plat_sem_t plat_os_sem_create(int ready);
void       plat_os_sem_take(plat_sem_t s, uint32_t timeout_ms);   /* 超时也继续执行 */
void       plat_os_sem_give_isr(plat_sem_t s);                    /* 中断里调用 */
void       plat_os_delay_ms(uint32_t ms);
uint32_t   plat_os_tick_ms(void);

#if PLAT_ENABLE_MEM_LOCK
void plat_os_mem_lock(void);
void plat_os_mem_unlock(void);
#else
#define plat_os_mem_lock()    do { } while (0)
#define plat_os_mem_unlock()  do { } while (0)
#endif

#else  /* ---------------- 裸机：空实现 ---------------- */

typedef int plat_sem_t;

#define plat_os_sem_create(ready)        ((void)(ready), (plat_sem_t)0)
#define plat_os_sem_take(s, ms)          do { (void)(s); (void)(ms); } while (0)
#define plat_os_sem_give_isr(s)          do { (void)(s); } while (0)
#define plat_os_mem_lock()               do { } while (0)
#define plat_os_mem_unlock()             do { } while (0)

#endif /* PLAT_USE_RTOS */

#ifdef __cplusplus
}
#endif

#endif /* __PLAT_H */
