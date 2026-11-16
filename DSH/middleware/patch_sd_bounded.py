#!/usr/bin/env python3
"""Make the vendor SD block read/write bounded (they otherwise spin forever).

Patch target: Drivers/BSP/SDMMC/sdmmc_sdcard.c
Run from the project root:  python DSH/middleware/patch_sd_bounded.py
"""
import io
import re

PATH = "Drivers/BSP/SDMMC/sdmmc_sdcard.c"

READ = r'''uint8_t sd_read_disk(uint8_t *pbuf, uint32_t saddr, uint32_t cnt)
{
    uint8_t  sta;
    uint32_t guard = 2000000u;      /* bounded busy wait (~few ms after HAL returns) */

    /* NOTE: interrupts are intentionally NOT disabled here: the HAL is driven in
     * polling mode and the original sys_intx_disable() + delay_ms() combination
     * would hang (delay_ms needs SysTick). */
    sta = (uint8_t)HAL_SD_ReadBlocks(&g_sd_handle, (uint8_t *)pbuf, saddr, cnt, 1000u);

    while ((get_sd_card_state() != SD_TRANSFER_OK) && (guard != 0u))
    {
        guard--;
    }

    if (guard == 0u)
    {
        return 1u;
    }

    return (sta == HAL_OK) ? 0u : 1u;
}'''

WRITE = r'''uint8_t sd_write_disk(uint8_t *pbuf, uint32_t saddr, uint32_t cnt)
{
    uint8_t  sta;
    uint32_t guard = 2000000u;

    sta = (uint8_t)HAL_SD_WriteBlocks(&g_sd_handle, (uint8_t *)pbuf, saddr, cnt, 1000u);

    while ((get_sd_card_state() != SD_TRANSFER_OK) && (guard != 0u))
    {
        guard--;
    }

    if (guard == 0u)
    {
        return 1u;
    }

    return (sta == HAL_OK) ? 0u : 1u;
}'''


def replace_func(src, name, new_body):
    start = src.index(f"uint8_t {name}(")
    # find the closing brace of the function: first "\n}\n" after start
    end = src.index("\n}\n", start) + 3
    return src[:start] + new_body + "\n" + src[end:]


def main():
    s = io.open(PATH, encoding="latin-1").read()
    s = replace_func(s, "sd_read_disk", READ)
    s = replace_func(s, "sd_write_disk", WRITE)
    io.open(PATH, "w", encoding="latin-1", newline="").write(s)
    print("sd_read_disk / sd_write_disk rewritten with bounded waits")


if __name__ == "__main__":
    main()
