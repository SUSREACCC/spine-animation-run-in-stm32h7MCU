/**
 ****************************************************************************************************
 * @file        selftest.c
 * @brief       Board-level driver self-test: MPU/SDRAM, LCD(LTDC+DMA2D), QSPI NOR, SD card.
 * @note        Console output: USART1 (PA9/PA10) @115200 -> CH340 -> COM11
 *              All comments kept ASCII so the file is encoding-safe for AC5 + uVision.
 ****************************************************************************************************
 */

#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "./BSP/MPU/mpu.h"
#include "./BSP/SDRAM/sdram.h"
#include "./BSP/LCD/lcd.h"
#include "./BSP/LCD/ltdc.h"
#include "./BSP/LED/led.h"
#include "./BSP/QSPI/qspi.h"
#include "./BSP/NORFLASH/norflash.h"
#include "./BSP/SDMMC/sdmmc_sdcard.h"
#include "./FATFS/source/ff.h"
#include <string.h>
#include "spine_test.h"
#include "spine_api.h"
#include "spine_demo.h"
#include "plat/plat.h"
#include "selftest.h"
#include "test_cfg.h"

#if TEST_TOUCH
#include "./BSP/TOUCH/touch.h"
#endif
#include "spine_ik_test.h"
#include "spine_anim_test.h"
#include "spine_anim_seq.h"
#include "spine_ik_interactive.h"

/*--------------------------------------------------------------- constants */
#define SDRAM_BASE          ((uint32_t)0xC0000000u)
#define SDRAM_SIZE          (32u * 1024u * 1024u)
#define SDRAM_STEP          (16u * 1024u)

#define FB_ADDR             ((uint32_t)0xC0000000u)
#define FB_BYTES            (800u * 480u * 2u)

#define QSPI_TEST_ADDR      (8u * 1024u * 1024u)    /* 8 MB offset  */
#define QSPI_TEST_LEN       (4096u)

/* Set to 1 only when debugging the SD socket on the bench: the 1-bit retry
 * path can block for tens of seconds inside HAL_SD_Init(). */
#define SD_SELFTEST_1BIT_FALLBACK   0

#if SD_BOARD_BUS4
#define SD_BUS_NAME "4-bit"
#else
#define SD_BUS_NAME "1-bit"
#endif

/*--------------------------------------------------------------- state */
#define ST_PENDING   0xFFu

static uint8_t  g_rc_sdram = ST_PENDING;
static uint8_t  g_rc_lcd   = ST_PENDING;
static uint8_t  g_rc_qspi  = ST_PENDING;
static uint8_t  g_rc_sd    = ST_PENDING;
static uint8_t  g_rc_ffs   = ST_PENDING;

static uint16_t g_lcd_id   = 0;
static uint16_t g_flash_id = 0;
static uint32_t g_sd_mb    = 0;

static uint8_t  g_qspi_wr[QSPI_TEST_LEN];
static uint8_t  g_qspi_rd[QSPI_TEST_LEN];
static uint8_t  g_sd_buf[512];
/* 8 KB scratch buffer for the SD capability sweep */
static uint8_t  g_sd_rd[8192];
#define SD_SWEEP_SECTORS   16u


/*--------------------------------------------------------------- cache helpers
 * SDRAM region is configured as CACHEABLE+BUFFERABLE by mpu.c. DMA2D/LTDC do not
 * snoop the D-cache, so every transfer involving SDRAM must be bracketed:
 *   clean  (cpu dirty lines -> memory) before DMA2D fills
 *   invalidate (drop stale lines)      after  DMA2D fills
 *--------------------------------------------------------------- */
static void fb_clean(void)
{
    SCB_CleanDCache_by_Addr((uint32_t *)FB_ADDR, (int32_t)FB_BYTES);
}

static void fb_invalidate(void)
{
    SCB_InvalidateDCache_by_Addr((uint32_t *)FB_ADDR, (int32_t)FB_BYTES);
}

static void fb_fill(uint16_t sx, uint16_t sy, uint16_t ex, uint16_t ey, uint32_t color)
{
    fb_clean();
    lcd_fill(sx, sy, ex, ey, color);
    fb_invalidate();
}

static void fb_clear(uint32_t color)
{
    fb_clean();
    lcd_clear(color);
    fb_invalidate();
}

/*--------------------------------------------------------------- SDRAM */
static uint8_t test_sdram(void)
{
    volatile uint32_t *p = (volatile uint32_t *)SDRAM_BASE;
    uint32_t i;
    uint32_t err = 0;
    uint32_t n;
    uint32_t v;

    /* 1) address integrity: one marker every 16 KB across the whole 32 MB */
    n = SDRAM_SIZE / SDRAM_STEP;
    for (i = 0; i < n; i++)
    {
        *(volatile uint32_t *)(SDRAM_BASE + i * SDRAM_STEP) = (uint32_t)(i * 2654435761u) ^ 0x5A5A5A5Au;
    }
    for (i = 0; i < n; i++)
    {
        v = *(volatile uint32_t *)(SDRAM_BASE + i * SDRAM_STEP);
        if (v != ((uint32_t)(i * 2654435761u) ^ 0x5A5A5A5Au))
        {
            err++;
        }
    }
    printf("  addr scan : %lu checkpoints over %lu KB, %lu error(s)\r\n",
           (unsigned long)n, (unsigned long)(SDRAM_SIZE / 1024u), (unsigned long)err);

    /* 2) data integrity: fixed patterns + address pattern on the first 64 KB */
    for (i = 0; i < 16384u; i++) { p[i] = 0x55555555u; }
    for (i = 0; i < 16384u; i++) { if (p[i] != 0x55555555u) err++; }

    for (i = 0; i < 16384u; i++) { p[i] = 0xAAAAAAAAu; }
    for (i = 0; i < 16384u; i++) { if (p[i] != 0xAAAAAAAAu) err++; }

    for (i = 0; i < 16384u; i++) { p[i] = 0x00000000u; }
    for (i = 0; i < 16384u; i++) { if (p[i] != 0x00000000u) err++; }

    for (i = 0; i < 16384u; i++) { p[i] = 0xFFFFFFFFu; }
    for (i = 0; i < 16384u; i++) { if (p[i] != 0xFFFFFFFFu) err++; }

    for (i = 0; i < 16384u; i++) { p[i] = (uint32_t)(SDRAM_BASE + i * 4u); }
    for (i = 0; i < 16384u; i++) { if (p[i] != (uint32_t)(SDRAM_BASE + i * 4u)) err++; }

    printf("  pattern   : 64 KB x 5 patterns, total error(s) = %lu\r\n", (unsigned long)err);

    return (err == 0u) ? ST_OK : ST_FAIL;
}

/*--------------------------------------------------------------- LCD */
static uint8_t test_lcd(void)
{
    uint32_t rb;

    lcd_init();

    g_lcd_id = lcddev.id;
    printf("  panel id  : %04X, %ux%u\r\n", lcddev.id, lcddev.width, lcddev.height);

    if ((lcddev.width != 800u) || (lcddev.height != 480u))
    {
        return ST_FAIL;
    }

    /* round-trip a known colour through the SDRAM framebuffer */
    lcd_draw_point(10, 10, 0xF800u);            /* red    */
    fb_clean();
    rb = lcd_read_point(10, 10);
    if ((rb & 0xFFFFu) != 0xF800u)
    {
        printf("  pixel rb  : expected F800, got %04X\r\n", (unsigned int)(rb & 0xFFFFu));
        return ST_FAIL;
    }
    printf("  pixel rb  : F800 OK (framebuffer @ 0x%08lX)\r\n", (unsigned long)FB_ADDR);

    return ST_OK;
}

/*--------------------------------------------------------------- QSPI NOR */
static uint8_t test_qspi(void)
{
    uint32_t i;
    uint32_t err = 0;

    norflash_init();
    g_flash_id = norflash_read_id();
    printf("  flash id  : %04X\r\n", g_flash_id);

    if ((g_flash_id != W25Q128) && (g_flash_id != GD25Q128))
    {
        return ST_FAIL;
    }

    for (i = 0; i < QSPI_TEST_LEN; i++)
    {
        g_qspi_wr[i] = (uint8_t)((i * 7u) + 3u);
        g_qspi_rd[i] = 0;
    }

    norflash_write(g_qspi_wr, QSPI_TEST_ADDR, QSPI_TEST_LEN);
    norflash_read(g_qspi_rd, QSPI_TEST_ADDR, QSPI_TEST_LEN);

    for (i = 0; i < QSPI_TEST_LEN; i++)
    {
        if (g_qspi_wr[i] != g_qspi_rd[i])
        {
            err++;
        }
    }
    printf("  rw verify : %lu bytes @ 0x%06lX, %lu mismatch(es)\r\n",
           (unsigned long)QSPI_TEST_LEN, (unsigned long)QSPI_TEST_ADDR, (unsigned long)err);

    return (err == 0u) ? ST_OK : ST_FAIL;
}

/*--------------------------------------------------------------- SD card */
__attribute__((unused)) static uint8_t sd_try_read(uint32_t timeout_ms)
{
    uint8_t rc;
    uint32_t guard;

    rc = (uint8_t)HAL_SD_ReadBlocks(&g_sd_handle, g_sd_buf, 0u, 1u, timeout_ms);

    guard = 2000u;
    while ((get_sd_card_state() != SD_TRANSFER_OK) && (guard != 0u))
    {
        delay_ms(1);
        guard--;
    }

    return (rc == HAL_OK) ? 0u : 1u;
}

/* Runtime clock-divider change: SDMMC_CK = ker_ck / (2 * div).
 * Used to back off from 30 MHz if the card/socket cannot sustain it. */
static void sd_set_clock_div(uint32_t div)
{
    uint32_t clkcr = SDMMC1->CLKCR;
    clkcr &= ~SDMMC_CLKCR_CLKDIV;
    clkcr |= (div & SDMMC_CLKCR_CLKDIV);
    SDMMC1->CLKCR = clkcr;
}

/* SD 4-bit capability sweep: read 8 KB at each clock divider, verify the MBR
 * signature payload and report the measured throughput (DWT cycle counter). */
static void dwt_init(void)
{
    CoreDebug->DEMCR |= CoreDebug_DEMCR_TRCENA_Msk;
    DWT->CYCCNT = 0u;
    DWT->CTRL |= DWT_CTRL_CYCCNTENA_Msk;
}

static uint8_t test_sd(void)
{
    static const uint32_t div_list[3] = { 20u, 8u, 4u };      /* 6 / 15 / 30 MHz */
    static const uint32_t div_mhz[3]  = { 6u, 15u, 30u };
    HAL_SD_CardInfoTypeDef info;
    uint8_t ok = 0u;
    uint8_t best = 0xFFu;
    uint32_t i;
    uint32_t t0, t1, cycles, kbps;

    if (sd_init() != 0u)
    {
        printf("  sd_init   : no card / init failed -> SKIP\r\n");
        return ST_SKIP;
    }

    if (get_sd_card_info(&info) != 0u)
    {
        return ST_FAIL;
    }

    g_sd_mb = (uint32_t)(info.LogBlockNbr / 2048u);    /* 512 B blocks -> MB */
    printf("  card      : %lu MB, type=%lu, block=%lu B\r\n",
           (unsigned long)g_sd_mb, (unsigned long)info.CardType,
           (unsigned long)info.LogBlockSize);
    printf("  bus       : %s, sweep 6/15/30 MHz\r\n", SD_BUS_NAME);

    dwt_init();

    /* NOTE: the vendor sd_read_disk() spins forever when the card does not
     * return to SD_TRANSFER_OK, so we drive HAL_SD_ReadBlocks directly. */
    for (i = 0; i < 3u; i++)
    {
        uint8_t rc;
        uint32_t guard;

        sd_set_clock_div(div_list[i]);
        t0 = DWT->CYCCNT;
        rc = (uint8_t)HAL_SD_ReadBlocks(&g_sd_handle, g_sd_rd, 0u, SD_SWEEP_SECTORS, 3000u);
        t1 = DWT->CYCCNT;

        guard = 2000u;
        while ((get_sd_card_state() != SD_TRANSFER_OK) && (guard != 0u))
        {
            delay_ms(1);
            guard--;
        }

        if ((rc == HAL_OK) && (guard != 0u) && (g_sd_rd[510] == 0x55u) && (g_sd_rd[511] == 0xAAu))
        {
            cycles = t1 - t0;
            if (cycles == 0u) { cycles = 1u; }
            /* cycles -> KB/s at 480 MHz; 8 KB per run */
            kbps = (uint32_t)(((uint64_t)SD_SWEEP_SECTORS * 512u * 480000u) / cycles);
            printf("  div=%-2lu (%2lu MHz): OK   %lu KB/s  \r\n",
                   (unsigned long)div_list[i], (unsigned long)div_mhz[i],
                   (unsigned long)kbps);
            ok = 1u;
            best = i;                 /* keep the fastest passing divider */
        }
        else
        {
            printf("  div=%-2lu (%2lu MHz): FAIL err=0x%08lX  \r\n",
                   (unsigned long)div_list[i], (unsigned long)div_mhz[i],
                   (unsigned long)g_sd_handle.ErrorCode);
        }
    }

    if (ok == 0u)
    {
        return ST_FAIL;
    }

    g_sd_buf[0] = g_sd_rd[510];   /* MBR signature from the successful sector-0 read */
    g_sd_buf[1] = g_sd_rd[511];

    /* keep the fastest divider that worked */
    sd_set_clock_div(div_list[best]);

    /* stress: 32 x 8 KB spread across the card at the final clock */
    {
        uint32_t k;
        uint32_t bad = 0u;
        uint32_t t2 = DWT->CYCCNT;
        for (k = 0u; k < 32u; k++)
        {
            if (HAL_SD_ReadBlocks(&g_sd_handle, g_sd_rd, k * 4096u, SD_SWEEP_SECTORS, 3000u) != HAL_OK)
            {
                bad++;
            }
        }
        t2 = DWT->CYCCNT - t2;
        printf("  stress    : 32 x 8 KB over the card, %lu error(s), %lu KB/s\r\n",
               (unsigned long)bad,
               (unsigned long)((t2 == 0u) ? 0u : ((uint64_t)32u * 8192u * 468750u) / t2));
        if (bad != 0u)
        {
            return ST_FAIL;
        }
    }
    printf("  using     : %lu MHz, MBR sig=%02X%02X\r\n",
           (unsigned long)div_mhz[best], g_sd_buf[0], g_sd_buf[1]);

    return ST_OK;
}

/*--------------------------------------------------------------- FATFS */
static FATFS   g_fs;
static FIL     g_fil;
static DIR     g_dir;
static FILINFO g_fno;

/* open <dir>/<name> and read the first bytes; returns 1 on success */
static uint8_t fatfs_probe_file(const char *dir, const char *name)
{
    char path[96];
    UINT br = 0u;
    uint8_t head[16];

    if (dir[0] != 0)
    {
        sprintf(path, "0:/%s/%s", dir, name);
    }
    else
    {
        sprintf(path, "0:/%s", name);
    }

    if (f_open(&g_fil, path, FA_READ) != FR_OK)
    {
        printf("  read      : open failed: %s\r\n", path);
        return 0u;
    }

    if ((f_read(&g_fil, head, sizeof(head), &br) != FR_OK) || (br == 0u))
    {
        f_close(&g_fil);
        printf("  read      : short read: %s\r\n", path);
        return 0u;
    }

    printf("  read      : %s -> %u B, %02X %02X %02X %02X ...\r\n",
           path, (unsigned)br, head[0], head[1], head[2], head[3]);

    f_close(&g_fil);
    return 1u;
}

/* small self-cleaning write test: create -> read back -> verify -> delete */
static uint8_t fatfs_write_roundtrip(void)
{
    static const char *NAME = "0:/H7TEST.TXT";
    uint8_t  wr[512];
    uint8_t  rd[512];
    UINT     bw = 0u;
    UINT     br = 0u;
    uint16_t i;
    uint8_t  ok = 0u;

    for (i = 0u; i < sizeof(wr); i++)
    {
        wr[i] = (uint8_t)(i * 31u + 7u);
    }

    if (f_open(&g_fil, NAME, FA_CREATE_ALWAYS | FA_WRITE) != FR_OK)
    {
        printf("  write     : open failed (card write protected?)\r\n");
        return 0u;
    }

    if ((f_write(&g_fil, wr, sizeof(wr), &bw) == FR_OK) && (bw == sizeof(wr)) &&
        (f_sync(&g_fil) == FR_OK))
    {
        ok = 1u;
    }
    f_close(&g_fil);

    if (ok != 0u)
    {
        ok = 0u;
        if (f_open(&g_fil, NAME, FA_READ) == FR_OK)
        {
            if ((f_read(&g_fil, rd, sizeof(rd), &br) == FR_OK) && (br == sizeof(rd)) &&
                (memcmp(wr, rd, sizeof(wr)) == 0))
            {
                ok = 1u;
            }
            f_close(&g_fil);
        }
    }

    printf("  write     : 512 B -> readback %s, delete %s\r\n",
           (ok != 0u) ? "match" : "MISMATCH",
           (f_unlink(NAME) == FR_OK) ? "ok" : "failed");

    return ok;
}

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
    char    subdir[32];

    subdir[0] = 0;

    fr = f_mount(&g_fs, "0:", 1);
    if (fr != FR_OK)
    {
        printf("  f_mount 0:: error %u\r\n", (unsigned)fr);
        return ST_FAIL;
    }

    fr = f_getfree("0:", &fre_clust, 0);
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

        if (((g_fno.fattrib & AM_DIR) != 0u) && (subdir[0] == 0) &&
            (strcmp(g_fno.fname, ".") != 0) && (strcmp(g_fno.fname, "..") != 0) &&
            (strncmp(g_fno.fname, "System", 6) != 0))
        {
            strncpy(subdir, g_fno.fname, sizeof(subdir) - 1u);
            subdir[sizeof(subdir) - 1u] = 0;
        }

        if ((readok == 0u) && ((g_fno.fattrib & (AM_DIR | AM_SYS | AM_HID)) == 0u) &&
            (g_fno.fsize > 16u))
        {
            readok = fatfs_probe_file("", g_fno.fname);
        }
    }
    f_closedir(&g_dir);

    /* nothing readable at root: descend one level into the first directory */
    if ((readok == 0u) && (subdir[0] != 0))
    {
        char path[96];

        sprintf(path, "0:/%s", subdir);
        if (f_opendir(&g_dir, path) == FR_OK)
        {
            for (i = 0u; (i < 12u) && (readok == 0u); i++)
            {
                if ((f_readdir(&g_dir, &g_fno) != FR_OK) || (g_fno.fname[0] == 0))
                {
                    break;
                }
                if (((g_fno.fattrib & (AM_DIR | AM_SYS | AM_HID)) == 0u) && (g_fno.fsize > 16u))
                {
                    readok = fatfs_probe_file(subdir, g_fno.fname);
                }
            }
            f_closedir(&g_dir);
        }
    }

    printf("  entries   : %u listed, file read %s\r\n",
           (unsigned)nfiles, (readok != 0u) ? "OK" : "n/a");

    (void)fatfs_write_roundtrip();

    return (listed != 0u) ? ST_OK : ST_FAIL;
}

/*--------------------------------------------------------------- screen */
static const char *rc_str(uint8_t rc)
{
    if (rc == ST_OK)      { return "PASS"; }
    if (rc == ST_SKIP)    { return "SKIP"; }
    if (rc == ST_PENDING) { return "WAIT"; }
    return "FAIL";
}

static void draw_screen(void)
{
    static const uint16_t bars[8] =
    {
        0xFFFF, 0xFFE0, 0x07FF, 0x07E0, 0xF81F, 0xF800, 0x001F, 0x0000
    };
    char line[64];
    uint32_t i;

    /* the vendor font renderer fills the glyph box with g_back_color;
     * default is 0xFFFFFFFF which is not a valid RGB565 colour */
    g_back_color = 0x0000u;
    g_point_color = 0xFFFFu;

    fb_clear(0x0000u);                                        /* black background */

    for (i = 0; i < 8u; i++)
    {
        fb_fill((uint16_t)(i * 100u), 0u, (uint16_t)(i * 100u + 99u), 59u, bars[i]);
    }

    /* text is drawn by the CPU -> flush dirty cache lines at the end */
    lcd_show_string(10, 70,  780, 32, 32, "STM32H743 DRIVER BRING-UP", 0xFFFFu);

    sprintf(line, "LCD  : %s  id=%04X  %ux%u", rc_str(g_rc_lcd),
            g_lcd_id, lcddev.width, lcddev.height);
    lcd_show_string(10, 120, 780, 16, 16, line, 0xFFE0u);

    sprintf(line, "SDRAM: %s  32 MB @ 0xC0000000 (framebuffer)", rc_str(g_rc_sdram));
    lcd_show_string(10, 150, 780, 16, 16, line, 0xFFE0u);

    sprintf(line, "QSPI : %s  W25Q128 id=%04X  4 KB rw @ 8 MB", rc_str(g_rc_qspi), g_flash_id);
    lcd_show_string(10, 180, 780, 16, 16, line, 0xFFE0u);

    if (g_rc_sd == ST_SKIP)
    {
        sprintf(line, "SD   : SKIP  (no card inserted)");
    }
    else
    {
        sprintf(line, "SD   : %s  %lu MB", rc_str(g_rc_sd), (unsigned long)g_sd_mb);
    }
    lcd_show_string(10, 210, 780, 16, 16, line, 0xFFE0u);

    sprintf(line, "FATFS: %s  SD volume 0: mounted, root listed", rc_str(g_rc_ffs));
    lcd_show_string(10, 240, 780, 16, 16, line, 0xFFE0u);

    lcd_show_string(10, 290, 780, 24, 24, "Self-test finished, heartbeat running", 0x07FFu);

    fb_clean();
}

/*--------------------------------------------------------------- entry */
/*----------------------------------------------------------------- 新 API 演示 */

static void api_demo(void)
{
    const char *SKEL = "/spine/celestial-circus-pro.skel";
    const char *ATLAS = "/spine/celestial-circus-pro.atlas";

    spine_asset_t *asset = spine_asset_load(SKEL, ATLAS);

    if (asset == 0)
    {
        printf("[API] asset load failed\r\n");
        return;
    }

    printf("[API] animations:");
    for (int i = 0; i < spine_asset_anim_count(asset); i++)
    {
        printf(" %s", spine_asset_anim_name(asset, i));
    }
    printf("\r\n[API] texture bytes: %lu\r\n", (unsigned long)spine_asset_texture_bytes(asset));

    spine_instance_t *hero = spine_instance_create(asset);
    spine_instance_t *enemy = spine_instance_create(asset);

    spine_instance_play(hero, "swing", 1, 0);
    spine_instance_play(enemy, "wing-flap", 1, 0);

    /* 用包围盒把两个角色摆到左右两侧，缩放到 220 px 高 */
    float x0 = 0, y0 = 0, x1 = 0, y1 = 0;

    if (spine_instance_get_bounds(hero, &x0, &y0, &x1, &y1) == 0)
    {
        printf("[API] bounds failed\r\n");
        return;
    }

    float h = y1 - y0;
    float s = (h > 1.0f) ? (220.0f / h) : 1.0f;
    float cx = (x0 + x1) * 0.5f;
    float cy = (y0 + y1) * 0.5f;

    spine_instance_set_scale(hero, s);
    spine_instance_set_position(hero, 210.0f - cx * s, 250.0f - cy * s);

    spine_instance_set_scale(enemy, s);
    spine_instance_set_position(enemy, 590.0f - cx * s, 250.0f - cy * s);
    spine_instance_set_tint(enemy, 0xFFB0D0FFu);       /* 轻微冷色调，验证 tint */

    printf("[API] bounds=(%.0f,%.0f)-(%.0f,%.0f) scale=%.3f\r\n",
           (double)x0, (double)y0, (double)x1, (double)y1, (double)s);

    const int   frames = 300;
    const float dt = 1.0f / 60.0f;
    uint32_t    t0 = HAL_GetTick();

    for (int f = 0; f < frames; f++)
    {
        spine_instance_update(hero, dt);
        spine_instance_update(enemy, dt);

        spine_draw_begin(2);                 /* 半分辨率 */
        spine_instance_draw(hero);
        spine_instance_draw(enemy);
        spine_draw_end();
    }

    float ms = (float)(HAL_GetTick() - t0) / (float)frames;

    printf("[API] %d frames | %.2f ms/frame (%.1f fps) | instances=%d queue=%d\r\n",
           frames, (double)ms, (double)(1000.0f / ms),
           spine_world_instance_count(), spine_draw_queue_count());

    spine_instance_destroy(hero);
    spine_instance_destroy(enemy);
    spine_asset_free(asset);

    printf("[API] after free: instances=%d\r\n", spine_world_instance_count());
    printf("[API] RESULT PASS\r\n");
}

void selftest_run(void)
{
    plat_init();        /* 裸机为空实现；RTOS 下建立同步对象并打开 LTDC 中断 */

    uint32_t beat = 0;
    uint32_t i;
    char line[64];

    /* The USART TX pin is high-Z until usart_init() muxes it; some USB-UART
     * bridges (CH340 + host driver) need a short idle period before they accept
     * data again after a reset, so the banner is repeated a few times. */
    for (i = 0; i < 3u; i++)
    {
        delay_ms(150);
        printf("\r\n\r\n");
        printf("==============================================\r\n");
        printf(" STM32H743 DRIVER SELFTEST\r\n");
        printf(" build: %s %s\r\n", __DATE__, __TIME__);
        printf("==============================================\r\n");
    }

    led_init();
    LED0(0);

    printf("[1/5] MPU + SDRAM\r\n");
    mpu_memory_protection();
    sdram_init();
    g_rc_sdram = test_sdram();

    printf("[2/5] LCD (LTDC + DMA2D + SDRAM framebuffer)\r\n");
    g_rc_lcd = test_lcd();

    /* Paint the screen right away so that a later stall (e.g. SD socket)
     * cannot leave the panel blank.  It is repainted with final results below. */
    draw_screen();

    printf("[3/5] QSPI NOR flash\r\n");
    g_rc_qspi = test_qspi();

    printf("[4/5] SD card (SDMMC1, %s)\r\n", SD_BUS_NAME);
    g_rc_sd = test_sd();

    printf("[5/5] FATFS on SD volume 0:\r\n");
    g_rc_ffs = test_fatfs();

    printf("----------------------------------------------\r\n");
    printf("RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s FATFS=%s\r\n",
           rc_str(g_rc_sdram), rc_str(g_rc_lcd), rc_str(g_rc_qspi), rc_str(g_rc_sd),
           rc_str(g_rc_ffs));

    draw_screen();

    sprintf(line, "RESULT SDRAM=%s LCD=%s QSPI=%s SD=%s FATFS=%s",
            rc_str(g_rc_sdram), rc_str(g_rc_lcd), rc_str(g_rc_qspi), rc_str(g_rc_sd),
            rc_str(g_rc_ffs));
    printf("%s\r\n", line);
    printf("----------------------------------------------\r\n");

    delay_ms(1500);
    printf("[TGX] starting 2D render test\r\n");
    printf("----------------------------------------------\r\n");

    /* ---- Spine 集成测试（素材需放在 SD 卡 /spine/ 下）---- */
    /* ---- walk 动画实时播放（双缓冲，60fps，15 秒）---- */
    /* 帧缓冲写带宽基准（MPU 三种属性） */
#if TEST_FBBENCH
    fb_bench();
#endif

    /* 基准显示 64 位存储下写穿最快（170 vs 150 MB/s），正式启用 */
    fb_mpu_set(2);

    /* ---- 以下测试由 User/test_cfg.h 的宏逐个开关 ---- */

#if TEST_SHEET
    /* 素材总览：打印动画列表 + 渲染全部角色 */
    (void)spine_anim_sheet("/spine/celestial-circus-pro.skel",
                           "/spine/celestial-circus-pro.atlas", 0.5f);
#endif

#if TEST_GRAVITY
    /* 重力方向：给 hair-back 注入物理约束，重力绕圈 */
    (void)spine_gravity_test("/spine/celestial-circus-pro.skel",
                             "/spine/celestial-circus-pro.atlas",
                             NULL, 60, 10, 1, "hair-back");
#endif

#if TEST_DUO
    /* 双角色：全分辨率 2 轮 + 半分辨率 2 轮 */
    (void)spine_play_duo("/spine/celestial-circus-pro.skel",
                         "/spine/celestial-circus-pro.atlas",
                         "swing", "wing-flap", 60, 4, 1, 2);
    (void)spine_play_duo("/spine/celestial-circus-pro.skel",
                         "/spine/celestial-circus-pro.atlas",
                         "swing", "wing-flap", 60, 4, 2, 2);
#endif

#if TEST_API_DEMO
    api_demo();
#endif

#if TEST_IK
    /* IK 目标驱动：spineboy 素材（7 个 IK 约束），画 3 秒让效果可见 */
    (void)spine_ik_test("/spine/spineboy-pro.skel",
                        "/spine/spineboy-pma.atlas",
                        "walk", 5, 1);
#endif

#if TEST_ANIM_MIX
    /* 动画衔接：默认过渡 / 当前动画名 / 进度接回 / 排队下一段 */
    (void)spine_anim_test("/spine/spineboy-pro.skel",
                          "/spine/spineboy-pma.atlas", 30);
#endif

#if TEST_ANIM_SEQ
    /* 4 段动画序列；aim 段触摸驱动 aim-ik */
    (void)spine_anim_seq("/spine/spineboy-pro.skel", "/spine/spineboy-pma.atlas");
#endif

#if TEST_IK_INTERACTIVE
    /* 交互：点击屏幕把 IK 目标挪到点击处 */
#if TEST_TOUCH
    printf("\r\n[IKT] tp_init() = %u\r\n", (unsigned)tp_init());
#else
    printf("\r\n[IKT] TEST_TOUCH=0，触摸未初始化\r\n");
#endif
    (void)spine_ik_interactive("/spine/spineboy-pro.skel",
                               "/spine/spineboy-pma.atlas",
                               "rear-leg-ik", TEST_IK_TOUCH_SECONDS);
#endif

#if TEST_DEMO
    /* 6 场景循环展示（不返回） */
    spine_demo_run();
#endif

#if TEST_HEARTBEAT
    printf("heartbeat start\r\n");

    while (1)
    {
        LED0_TOGGLE();
        delay_ms(1000);
        beat++;
        printf("alive %lu\r\n", (unsigned long)beat);
    }
#endif

    printf("heartbeat start\r\n");

    while (1)
    {
        LED0_TOGGLE();
        delay_ms(1000);
        beat++;
        printf("alive %lu\r\n", (unsigned long)beat);
    }


}
