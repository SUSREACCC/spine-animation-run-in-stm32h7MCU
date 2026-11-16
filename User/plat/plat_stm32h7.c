/**
 ****************************************************************************************************
 * @file        plat_stm32h7.c
 * @brief       平台抽象层实现：STM32H743IIT6 + W9825G6KH SDRAM + LTDC + FatFs
 *
 * 这是"换平台时唯一需要重写"的文件。库（spine_api / spine_platform / raster2d / spine-cpp）
 * 不包含任何本文件的细节。
 *
 * 裸机 / RTOS 两种模式由 plat_cfg.h 的 PLAT_USE_RTOS 切换：
 *   裸机：等垂直回扫用轮询 VBR
 *   RTOS：等 LTDC 重装中断给出的信号量，等待期间让出 CPU
 *
 * 打开 PLAT_USE_RTOS 时还需要一个 OS 适配文件（实现 plat_os_* 钩子），
 * FreeRTOS 版本见同目录 plat_os_freertos.c.template。
 ****************************************************************************************************
 */

#include <string.h>
#include <stdio.h>
#include <stdarg.h>

#include "plat.h"

#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/LCD/lcd.h"
#include "./FATFS/source/ff.h"

/*----------------------------------------------------------------- 1. 内存 */

/* 当前板的 SDRAM 布局（32 MB @ 0xC0000000）：
 *   0xC0000000 + 2 MB  : 帧缓冲 A（链接脚本保留）
 *   0xC0200000 + 8 MB  : spine 堆
 *   0xC0A00000 + 16 MB : 资源区
 *   0xC1A00000 / 0xC1B00000 : 帧缓冲 B / C
 */
#define PLAT_HEAP_BASE   0xC0200000u
#define PLAT_HEAP_SIZE   (8u * 1024u * 1024u)
#define PLAT_ARENA_BASE  0xC0A00000u
#define PLAT_ARENA_SIZE  (16u * 1024u * 1024u)

void plat_mem_pools(void **heap, size_t *heap_size, void **arena, size_t *arena_size)
{
    *heap = (void *)PLAT_HEAP_BASE;
    *heap_size = (size_t)PLAT_HEAP_SIZE;
    *arena = (void *)PLAT_ARENA_BASE;
    *arena_size = (size_t)PLAT_ARENA_SIZE;
}

/*----------------------------------------------------------------- 2. 文件系统（FatFs） */

#define PLAT_FILE_SLOTS 4

struct plat_file
{
    FIL fil;
    int used;
};

static plat_file_t s_files[PLAT_FILE_SLOTS];

int plat_file_open(plat_file_t **f, const char *path)
{
    for (int i = 0; i < PLAT_FILE_SLOTS; i++)
    {
        if (s_files[i].used == 0)
        {
            if (f_open(&s_files[i].fil, path, FA_READ) != FR_OK)
            {
                return -1;
            }

            s_files[i].used = 1;
            *f = &s_files[i];
            return 0;
        }
    }

    return -2;                      /* 句柄耗尽 */
}

int plat_file_read(plat_file_t *f, void *buf, size_t bytes, size_t *got)
{
    UINT br = 0;

    if ((f == NULL) || (!f->used))
    {
        return -1;
    }

    if (f_read(&f->fil, buf, (UINT)bytes, &br) != FR_OK)
    {
        return -1;
    }

    if (got != NULL)
    {
        *got = (size_t)br;
    }
    return 0;
}

int plat_file_size(plat_file_t *f, size_t *bytes)
{
    if ((f == NULL) || (!f->used) || (bytes == NULL))
    {
        return -1;
    }

    *bytes = (size_t)f_size(&f->fil);
    return 0;
}

void plat_file_close(plat_file_t *f)
{
    if ((f != NULL) && f->used)
    {
        f_close(&f->fil);
        f->used = 0;
    }
}

/*----------------------------------------------------------------- 3. 显示（LTDC） */

static plat_sem_t s_reload_sem = 0;

int plat_display_w(void) { return PLAT_SCREEN_W; }
int plat_display_h(void) { return PLAT_SCREEN_H; }

int plat_fb_count(void) { return PLAT_FB_COUNT; }

void *plat_fb_addr(int index)
{
    switch (index)
    {
        case 0:  return (void *)0xC0000000u;
        case 1:  return (void *)0xC1A00000u;
        case 2:  return (void *)0xC1B00000u;
        default: return NULL;
    }
}

void plat_init(void)
{
#if PLAT_USE_RTOS
    /* 二值信号量：初始可用，保证第一帧不用等 */
    s_reload_sem = plat_os_sem_create(1);

    /* 打开 LTDC 寄存器重装中断：影子寄存器生效（即切换完成）时触发 */
    LTDC->IER |= LTDC_IER_RRIE;
    HAL_NVIC_SetPriority(LTDC_IRQn, 6, 0);
    HAL_NVIC_EnableIRQ(LTDC_IRQn);
#endif
}

void plat_fb_wait_ready(void)
{
#if PLAT_USE_RTOS
    plat_os_sem_take(s_reload_sem, 100u);       /* 超时也继续，不让系统卡死 */
#else
    while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
    {
    }
#endif
}

void plat_fb_present(void *fb)
{
#if PLAT_PRESENT_BLOCKING
    plat_fb_wait_ready();
#endif

    LTDC_Layer1->CFBAR = (uint32_t)fb;
    LTDC->SRCR = LTDC_SRCR_VBR;

#if !PLAT_USE_RTOS
    /* 裸机：切换后仍按原行为等它生效，保证下一次不会写正在扫描的缓冲 */
    while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
    {
    }
#endif
}

#if PLAT_USE_RTOS
/* LTDC 重装完成中断：唤醒等 vsync 的任务。
 * 注意：工程里若另有 LTDC_IRQHandler 定义需要二选一。 */
void LTDC_IRQHandler(void)
{
    if ((LTDC->ISR & LTDC_ISR_RRIF) != 0u)
    {
        LTDC->ICR = LTDC_ICR_CRRIF;
        plat_os_sem_give_isr(s_reload_sem);
    }
}
#endif

/*----------------------------------------------------------------- 4. 缓存 + 帧缓冲缓存属性 */

static int s_fb_write_through = 0;

void plat_cache_clean(void *addr, size_t bytes)
{
    if ((addr == NULL) || (bytes == 0u))
    {
        return;
    }

    SCB_CleanInvalidateDCache_by_Addr((uint32_t *)addr, (int32_t)bytes);
}

void plat_cache_invalidate(void *addr, size_t bytes)
{
    if ((addr == NULL) || (bytes == 0u))
    {
        return;
    }

    SCB_InvalidateDCache_by_Addr((uint32_t *)addr, (int32_t)bytes);
}

/**
 * 切换帧缓冲所在 MPU 区域的缓存属性。
 *   mode 0 : write-back（写分配）—— 默认
 *   mode 1 : non-cacheable
 *   mode 2 : write-through（不写分配）—— 写直达 SDRAM，无需手动冲刷
 *
 * RTOS 下若在运行期调用，必须保证没有其它任务正在写帧缓冲。
 */
void plat_fb_set_cache_mode(int mode)
{
    uint32_t attr = (3u << 24);                 /* AP = full access, XN = 0 */

    s_fb_write_through = (mode == 2);

    if (mode == 0)
    {
        attr |= (1u << 17) | (1u << 16);        /* WB: C=1 B=1 */
    }
    else if (mode == 2)
    {
        attr |= (1u << 17);                     /* WT: C=1 B=0 */
    }

    HAL_MPU_Disable();
    MPU->RNR = 8u;
    MPU->RBAR = 0xC0000000u;
    MPU->RASR = (1u << 0) | (0x14u << 1) | attr;    /* 2 MB：帧缓冲 A */
    MPU->RNR = 9u;
    MPU->RBAR = 0xC1A00000u;
    MPU->RASR = (1u << 0) | (0x13u << 1) | attr;    /* 1 MB：帧缓冲 B */
    MPU->RNR = 10u;
    MPU->RBAR = 0xC1B00000u;
    MPU->RASR = (1u << 0) | (0x13u << 1) | attr;    /* 1 MB：帧缓冲 C */
    HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);

    SCB_CleanInvalidateDCache();
}

int plat_fb_need_cache_clean(void)
{
    return (s_fb_write_through == 0) ? 1 : 0;
}

/*----------------------------------------------------------------- 5. 时间 */

uint32_t plat_now_ms(void)
{
#if PLAT_USE_RTOS
    return plat_os_tick_ms();
#else
    return HAL_GetTick();
#endif
}

uint64_t plat_now_us(void)
{
    /* DWT 周期计数器（480 MHz）。RTOS 下同样可用，与调度无关。 */
    static uint32_t last = 0;
    static uint64_t acc = 0;
    uint32_t now = DWT->CYCCNT;

    acc += (uint32_t)(now - last);
    last = now;

    return acc / 480u;
}

void plat_delay_ms(uint32_t ms)
{
#if PLAT_USE_RTOS
    plat_os_delay_ms(ms);           /* 让出 CPU */
#else
    HAL_Delay(ms);
#endif
}

/*----------------------------------------------------------------- 6. 日志 */

void plat_log(const char *fmt, ...)
{
    va_list ap;

    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
}
