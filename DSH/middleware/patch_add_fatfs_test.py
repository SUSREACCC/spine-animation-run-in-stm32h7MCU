#!/usr/bin/env python3
"""Wire a FatFs self-test step into User/selftest.c.

Run from the project root:  python DSH/middleware/patch_add_fatfs_test.py
"""
import io

PATH = "User/selftest.c"

FUNC = r'''
/*--------------------------------------------------------------- FATFS */
static FATFS   g_fs;
static FIL     g_fil;
static DIR     g_dir;
static FILINFO g_fno;

static uint8_t test_fatfs(void)
{
    FRESULT fr;
    DWORD   fre_clust = 0;
    DWORD   tot_sect;
    DWORD   fre_sect;
    UINT    i;
    UINT    nfiles = 0;
    uint8_t listed = 0;
    uint8_t readok = 0;

    fr = f_mount(&g_fs, "0:", 1);
    if (fr != FR_OK)
    {
        printf("  f_mount 0:: error %u\r\n", (unsigned)fr);
        return ST_FAIL;
    }

    fr = f_getfree("0:", &fre_clust, &g_fs);
    if (fr == FR_OK)
    {
        tot_sect = (DWORD)(g_fs.n_fatent - 2u) * g_fs.csize;
        fre_sect = fre_clust * g_fs.csize;
        printf("  volume    : FAT%d, total %lu MB, free %lu MB\r\n",
               (g_fs.fs_type == FS_FAT32) ? 32 : (int)g_fs.fs_type,
               (unsigned long)(tot_sect / 2048u), (unsigned long)(fre_sect / 2048u));
    }
    else
    {
        printf("  f_getfree : error %u\r\n", (unsigned)fr);
    }

    fr = f_opendir(&g_dir, "0:/");
    if (fr != FR_OK)
    {
        printf("  f_opendir : error %u\r\n", (unsigned)fr);
        return ST_FAIL;
    }

    for (i = 0u; i < 12u; i++)
    {
        fr = f_readdir(&g_dir, &g_fno);
        if ((fr != FR_OK) || (g_fno.fname[0] == 0))
        {
            break;
        }
        printf("   %s%s  %lu B\r\n", g_fno.fname,
               ((g_fno.fattrib & AM_DIR) != 0u) ? "/" : " ",
               (unsigned long)g_fno.fsize);
        nfiles++;
        listed = 1u;

        if ((readok == 0u) && ((g_fno.fattrib & (AM_DIR | AM_SYS | AM_HID)) == 0u) &&
            (g_fno.fsize > 32u))
        {
            if (f_open(&g_fil, g_fno.fname, FA_READ) == FR_OK)
            {
                UINT br = 0u;
                uint8_t head[16];

                if ((f_read(&g_fil, head, sizeof(head), &br) == FR_OK) && (br > 0u))
                {
                    printf("  read      : %s -> %u B, %02X %02X %02X %02X ...\r\n",
                           g_fno.fname, (unsigned)br,
                           head[0], head[1], head[2], head[3]);
                    readok = 1u;
                }
                f_close(&g_fil);
            }
        }
    }
    f_closedir(&g_dir);

    printf("  entries   : %u listed, first-file read %s\r\n",
           (unsigned)nfiles, (readok != 0u) ? "OK" : "n/a");

    return (listed != 0u) ? ST_OK : ST_FAIL;
}
'''

src = io.open(PATH, encoding="utf-8").read()

# 1) include ff.h
if "FATFS/source/ff.h" not in src:
    src = src.replace('#include "selftest.h"',
                      '#include "./FATFS/source/ff.h"\n#include "selftest.h"', 1)

# 2) result variable
src = src.replace("static uint8_t  g_rc_sd    = ST_PENDING;",
                  "static uint8_t  g_rc_sd    = ST_PENDING;\nstatic uint8_t  g_rc_ffs   = ST_PENDING;", 1)

# 3) insert the test function before the screen section
marker = "/*--------------------------------------------------------------- screen */"
if "static uint8_t test_fatfs(void)" not in src:
    src = src.replace(marker, FUNC.strip() + "\n\n" + marker, 1)

# 4) screen: add a FATFS line after the SD line
old_sd = '''    lcd_show_string(10, 210, 780, 16, 16, line, 0xFFE0u);
'''
new_sd = '''    lcd_show_string(10, 210, 780, 16, 16, line, 0xFFE0u);

    sprintf(line, "FATFS: %s  SD volume 0: mounted, root listed", rc_str(g_rc_ffs));
    lcd_show_string(10, 240, 780, 16, 16, line, 0xFFE0u);
'''
if "FATFS: %s" not in src:
    src = src.replace(old_sd, new_sd, 1)

# 5) run step 5/5 and include it in the summary
src = src.replace('printf("[4/4] SD card (SDMMC1, %s)\\r\\n", SD_BUS_NAME);',
                  'printf("[4/5] SD card (SDMMC1, %s)\\r\\n", SD_BUS_NAME);', 1)
src = src.replace('printf("[1/4] MPU + SDRAM\\r\\n");', 'printf("[1/5] MPU + SDRAM\\r\\n");', 1)
src = src.replace('printf("[2/4] LCD (LTDC + DMA2D + SDRAM framebuffer)\\r\\n");',
                  'printf("[2/5] LCD (LTDC + DMA2D + SDRAM framebuffer)\\r\\n");', 1)
src = src.replace('printf("[3/4] QSPI NOR flash\\r\\n");', 'printf("[3/5] QSPI NOR flash\\r\\n");', 1)

old_tail = '''    printf("----------------------------------------------\\r\\n");
    printf("RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s\\r\\n",
           rc_str(g_rc_sdram), rc_str(g_rc_lcd), rc_str(g_rc_qspi), rc_str(g_rc_sd));'''
new_tail = '''    printf("[5/5] FATFS on SD volume 0:\\r\\n");
    g_rc_ffs = test_fatfs();

    printf("----------------------------------------------\\r\\n");
    printf("RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s FATFS=%s\\r\\n",
           rc_str(g_rc_sdram), rc_str(g_rc_lcd), rc_str(g_rc_qspi), rc_str(g_rc_sd),
           rc_str(g_rc_ffs));'''
if "[5/5] FATFS" not in src:
    src = src.replace(old_tail, new_tail, 1)

# summary string built with sprintf
src = src.replace('sprintf(line, "RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s",\n            rc_str(g_rc_sdram), rc_str(g_rc_lcd), rc_str(g_rc_qspi), rc_str(g_rc_sd));',
                  'sprintf(line, "RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s FATFS=%s",\n            rc_str(g_rc_sdram), rc_str(g_rc_lcd), rc_str(g_rc_qspi), rc_str(g_rc_sd),\n            rc_str(g_rc_ffs));', 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("selftest.c: FatFs step wired in")
