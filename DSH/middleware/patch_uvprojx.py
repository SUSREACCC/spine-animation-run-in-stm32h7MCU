#!/usr/bin/env python3
"""Patch STM32H743.uvprojx: add BSP source groups + extra HAL modules + selftest.c.

The uVision project file is byte-preserving edited (latin-1 round-trip) so that the
GBK-encoded Chinese text elsewhere in the file is not corrupted.

Usage:
    python patch_uvprojx.py <path-to.uvprojx>
"""
import sys

USER_GROUP = "User"
HAL_GROUP = "Drivers/STM32H7xx_HAL_Driver"

USER_FILES = [
    ("selftest.c", r"..\..\User\selftest.c"),
]

BSP_GROUPS = [
    ("Drivers/BSP/MPU",      [("mpu.c",      r"..\..\Drivers\BSP\MPU\mpu.c")]),
    ("Drivers/BSP/SDRAM",    [("sdram.c",    r"..\..\Drivers\BSP\SDRAM\sdram.c")]),
    ("Drivers/BSP/LCD",      [("lcd.c",      r"..\..\Drivers\BSP\LCD\lcd.c"),
                              ("ltdc.c",     r"..\..\Drivers\BSP\LCD\ltdc.c"),
                              ("tft_spi.c",  r"..\..\Drivers\BSP\LCD\tft_spi.c")]),
    ("Drivers/BSP/QSPI",     [("qspi.c",     r"..\..\Drivers\BSP\QSPI\qspi.c")]),
    ("Drivers/BSP/NORFLASH", [("norflash.c", r"..\..\Drivers\BSP\NORFLASH\norflash.c")]),
    ("Drivers/BSP/SDMMC",    [("sdmmc_sdcard.c", r"..\..\Drivers\BSP\SDMMC\sdmmc_sdcard.c")]),
    ("Drivers/BSP/LED",      [("led.c",      r"..\..\Drivers\BSP\LED\led.c")]),
]

MIDDLEWARE_GROUPS = [
    ("Middlewares/FATFS", [
        ("ff.c",       r"..\..\Middlewares\FATFS\source\ff.c"),
        ("ffunicode.c", r"..\..\Middlewares\FATFS\source\ffunicode.c"),
        ("ffsystem.c", r"..\..\Middlewares\FATFS\source\ffsystem.c"),
        ("diskio.c",   r"..\..\Middlewares\FATFS\source\diskio.c"),
    ]),
]

HAL_FILES = [
    ("stm32h7xx_hal_ltdc.c",     r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_ltdc.c"),
    ("stm32h7xx_hal_ltdc_ex.c",  r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_ltdc_ex.c"),
    ("stm32h7xx_hal_dma2d.c",    r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_dma2d.c"),
    ("stm32h7xx_hal_sdram.c",    r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_sdram.c"),
    ("stm32h7xx_hal_sram.c",     r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_sram.c"),
    ("stm32h7xx_hal_qspi.c",     r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_qspi.c"),
    ("stm32h7xx_hal_mdma.c",     r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_mdma.c"),
    ("stm32h7xx_hal_sd.c",       r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_sd.c"),
    ("stm32h7xx_hal_sd_ex.c",    r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_sd_ex.c"),
    ("stm32h7xx_hal_dma_ex.c",   r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_dma_ex.c"),
    ("stm32h7xx_hal_tim.c",      r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_tim.c"),
    ("stm32h7xx_hal_tim_ex.c",   r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_hal_tim_ex.c"),
    # low-level drivers required by HAL SDRAM/SRAM (FMC) and HAL SD (SDMMC)
    ("stm32h7xx_ll_fmc.c",       r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_ll_fmc.c"),
    ("stm32h7xx_ll_sdmmc.c",     r"..\..\Drivers\STM32H7xx_HAL_Driver\Src\stm32h7xx_ll_sdmmc.c"),
]

IND = "  "


def file_block(name, path, indent):
    return (f"{indent}<File>\n"
            f"{indent}  <FileName>{name}</FileName>\n"
            f"{indent}  <FileType>1</FileType>\n"
            f"{indent}  <FilePath>{path}</FilePath>\n"
            f"{indent}</File>\n")


def insert_into_group(s, group, entries):
    """Insert <File> entries at the end of the given group's <Files> block."""
    key = f"<GroupName>{group}</GroupName>"
    if key not in s:
        raise SystemExit(f"group not found: {group}")
    i = s.index(key)
    end = s.index(f"{IND*4}</Files>", i)          # '            </Files>'
    existing = s[i:end]
    block = ""
    for name, path in entries:
        if f"<FileName>{name}</FileName>" in existing:
            continue
        block += file_block(name, path, IND * 6)  # 12 spaces
    if not block:
        return s, 0
    return s[:end] + block + s[end:], block.count("<File>")


def main(path):
    with open(path, encoding="latin-1") as f:
        s = f.read()

    added = 0
    s, n = insert_into_group(s, USER_GROUP, USER_FILES)
    added += n
    s, n = insert_into_group(s, HAL_GROUP, HAL_FILES)
    added += n

    # new BSP groups, inserted right before </Groups>
    blocks = ""
    for group, entries in BSP_GROUPS + MIDDLEWARE_GROUPS:
        if f"<GroupName>{group}</GroupName>" in s:
            continue
        b = f"{IND*4}<Group>\n{IND*5}<GroupName>{group}</GroupName>\n{IND*5}<Files>\n"
        for name, p in entries:
            b += file_block(name, p, IND * 6)
        b += f"{IND*5}</Files>\n{IND*4}</Group>\n"
        blocks += b
        added += len(entries)
    s = s.replace(f"{IND*3}</Groups>", blocks + f"{IND*3}</Groups>", 1)

    with open(path, "w", encoding="latin-1", newline="") as f:
        f.write(s)
    print(f"patched {path}: {added} file entries added")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "STM32H743.uvprojx")
