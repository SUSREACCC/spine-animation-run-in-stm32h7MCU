/**
 ****************************************************************************************************
 * @file        ffsystem.c
 * @brief       FatFs 平台适配层（时间 + 内存）
 * @note        不依赖开发板例程的 MALLOC 中间件，直接用 C 库 malloc/free。
 *              本项目使用 FF_USE_LFN == 1（静态 LFN 缓冲），内存函数仅在
 *              f_mkfs / 极小配置下被调用。
 ****************************************************************************************************
 */

#include "ff.h"
#include <stdlib.h>

/* FatFs 需要的时间戳：无 RTC 时返回固定值（0 = 1980-01-01） */
DWORD get_fattime(void)
{
    return 0;
}

void *ff_memalloc(UINT size)
{
    return malloc((size_t)size);
}

void ff_memfree(void *mfbuf)
{
    free(mfbuf);
}
