/**
 ****************************************************************************************************
 * @file        diskio.c
 * @brief       FatFs 底层介质访问层（本项目适配版）
 * @note        与开发板例程的区别：
 *               1) 去掉对厂商 MALLOC 中间件的依赖
 *               2) SD 读写失败时最多重试 3 次（原版是 while 死循环）
 *               3) disk_ioctl 正确回填扇区大小/数量（原版只返回 RES_OK，不写 buff）
 *               4) 卷 1（QSPI NOR）保留接口，默认 9 MB / 512 B 扇区
 *
 *  卷号：0 = SD 卡   1 = QSPI NOR（W25Q128 前 9 MB 作为 FAT 卷）
 ****************************************************************************************************
 */

#include "ff.h"
#include "diskio.h"
#include "./BSP/SDMMC/sdmmc_sdcard.h"
#include "./BSP/NORFLASH/norflash.h"

#define DEV_SD              0u
#define DEV_NOR             1u
#define DEV_COUNT           2u

#define SD_RETRY            3u

#define NOR_SECTOR_SIZE     512u
#define NOR_VOLUME_BYTES    (9u * 1024u * 1024u)
#define NOR_SECTOR_COUNT    (NOR_VOLUME_BYTES / NOR_SECTOR_SIZE)   /* 18432 */
#define NOR_ERASE_BLOCK_SECTORS 8u                                  /* 4 KB erase block */

/*------------------------------------------------------------------ status */

DSTATUS disk_status(BYTE pdrv)
{
    if (pdrv >= DEV_COUNT)
    {
        return STA_NOINIT;
    }
    return 0;
}

DSTATUS disk_initialize(BYTE pdrv)
{
    if (pdrv == DEV_SD)
    {
        return (sd_init() == 0u) ? 0u : STA_NOINIT;
    }

    if (pdrv == DEV_NOR)
    {
        norflash_init();
        return 0;
    }

    return STA_NOINIT;
}

/*------------------------------------------------------------------- read */

DRESULT disk_read(BYTE pdrv, BYTE *buff, LBA_t sector, UINT count)
{
    uint8_t tries;

    if ((count == 0u) || (buff == 0))
    {
        return RES_PARERR;
    }

    if (pdrv == DEV_SD)
    {
        for (tries = 0u; tries < SD_RETRY; tries++)
        {
            if (sd_read_disk(buff, (uint32_t)sector, count) == 0u)
            {
                return RES_OK;
            }
            sd_init();                                  /* 重新初始化后再试 */
        }
        return RES_ERROR;
    }

    if (pdrv == DEV_NOR)
    {
        while (count-- > 0u)
        {
            norflash_read(buff, (uint32_t)sector * NOR_SECTOR_SIZE, NOR_SECTOR_SIZE);
            sector++;
            buff += NOR_SECTOR_SIZE;
        }
        return RES_OK;
    }

    return RES_PARERR;
}

/*------------------------------------------------------------------ write */

DRESULT disk_write(BYTE pdrv, const BYTE *buff, LBA_t sector, UINT count)
{
    uint8_t tries;

    if ((count == 0u) || (buff == 0))
    {
        return RES_PARERR;
    }

    if (pdrv == DEV_SD)
    {
        for (tries = 0u; tries < SD_RETRY; tries++)
        {
            if (sd_write_disk((uint8_t *)buff, (uint32_t)sector, count) == 0u)
            {
                return RES_OK;
            }
            sd_init();
        }
        return RES_ERROR;
    }

    if (pdrv == DEV_NOR)
    {
        while (count-- > 0u)
        {
            norflash_write((uint8_t *)buff, (uint32_t)sector * NOR_SECTOR_SIZE, NOR_SECTOR_SIZE);
            sector++;
            buff += NOR_SECTOR_SIZE;
        }
        return RES_OK;
    }

    return RES_PARERR;
}

/*------------------------------------------------------------------ ioctl */

DRESULT disk_ioctl(BYTE pdrv, BYTE cmd, void *buff)
{
    HAL_SD_CardInfoTypeDef info;

    if (pdrv >= DEV_COUNT)
    {
        return RES_PARERR;
    }

    /* device independent commands */
    if (cmd == CTRL_SYNC)
    {
        return RES_OK;
    }

    /* device dependent commands */
    switch (cmd)
    {
        case GET_SECTOR_COUNT:
            if (pdrv == DEV_SD)
            {
                if (get_sd_card_info(&info) != 0u)
                {
                    return RES_ERROR;
                }
                *(LBA_t *)buff = (LBA_t)info.LogBlockNbr;
            }
            else
            {
                *(LBA_t *)buff = (LBA_t)NOR_SECTOR_COUNT;
            }
            return RES_OK;

        case GET_SECTOR_SIZE:
            *(WORD *)buff = (WORD)NOR_SECTOR_SIZE;
            return RES_OK;

        case GET_BLOCK_SIZE:
            *(DWORD *)buff = (pdrv == DEV_SD) ? 1u : (DWORD)NOR_ERASE_BLOCK_SECTORS;
            return RES_OK;

        default:
            return RES_PARERR;
    }
}
