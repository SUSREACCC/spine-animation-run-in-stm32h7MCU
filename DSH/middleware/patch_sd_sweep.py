#!/usr/bin/env python3
"""Replace test_sd() in User/selftest.c with a clock/throughput sweep version.

Run from the project root:  python DSH/middleware/patch_sd_sweep.py
"""
import io
import re

PATH = "User/selftest.c"
CRLF = chr(92) + "r" + chr(92) + "n"          # literal \r\n inside C string literals

NEW = r'''
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
        printf("  sd_init   : no card / init failed -> SKIP@CRLF@");
        return ST_SKIP;
    }

    if (get_sd_card_info(&info) != 0u)
    {
        return ST_FAIL;
    }

    g_sd_mb = (uint32_t)(info.LogBlockNbr / 2048u);    /* 512 B blocks -> MB */
    printf("  card      : %lu MB, type=%lu, block=%lu B@CRLF@",
           (unsigned long)g_sd_mb, (unsigned long)info.CardType,
           (unsigned long)info.LogBlockSize);
    printf("  bus       : %s, sweep 6/15/30 MHz@CRLF@", SD_BUS_NAME);

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
            printf("  div=%-2lu (%2lu MHz): OK   %lu KB/s  @CRLF@",
                   (unsigned long)div_list[i], (unsigned long)div_mhz[i],
                   (unsigned long)kbps);
            ok = 1u;
            if (best == 0xFFu) { best = i; }
        }
        else
        {
            printf("  div=%-2lu (%2lu MHz): FAIL err=0x%08lX  @CRLF@",
                   (unsigned long)div_list[i], (unsigned long)div_mhz[i],
                   (unsigned long)g_sd_handle.ErrorCode);
        }
    }

    if (ok == 0u)
    {
        return ST_FAIL;
    }

    /* keep the fastest divider that worked */
    sd_set_clock_div(div_list[best]);
    printf("  using     : %lu MHz, MBR sig=%02X%02X@CRLF@",
           (unsigned long)div_mhz[best], g_sd_rd[510], g_sd_rd[511]);

    g_sd_buf[0] = g_sd_rd[0];
    g_sd_buf[1] = g_sd_rd[1];
    g_sd_buf[2] = g_sd_rd[2];
    g_sd_buf[3] = g_sd_rd[3];
    return ST_OK;
}
'''.replace("@CRLF@", CRLF)

BUF = (
    "\n/* 8 KB scratch buffer for the SD capability sweep */\n"
    "static uint8_t  g_sd_rd[8192];\n"
    "#define SD_SWEEP_SECTORS   16u\n"
)

src = io.open(PATH, encoding="utf-8").read()
start = src.index("static uint8_t test_sd(void)")
end = src.index("/*--------------------------------------------------------------- screen */")
src = src[:start] + NEW.strip() + "\n\n" + src[end:]

# add the buffer right after the g_sd_buf declaration (once)
if "g_sd_rd" not in src.split("static uint8_t test_sd")[0]:
    src = src.replace("static uint8_t  g_sd_buf[512];",
                      "static uint8_t  g_sd_buf[512];" + BUF, 1)

io.open(PATH, "w", encoding="utf-8", newline="").write(src)
print("test_sd() replaced with sweep version")
