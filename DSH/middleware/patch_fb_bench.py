#!/usr/bin/env python3
"""Framebuffer write-bandwidth benchmark with runtime-switchable MPU attributes.

The framebuffer currently sits in the board MPU region 6 (SDRAM, 32 MB,
cacheable + bufferable => write-back with write-allocate).  Every write miss
therefore fetches a 32-byte cache line first, and every frame needs a cache
clean before the LTDC can see the pixels.

This adds three extra MPU regions (8/9/10) covering exactly the three
framebuffers and lets the benchmark switch them between:

    mode 0 : write-back  (C=1 B=1)  - current behaviour
    mode 1 : non-cacheable (C=0 B=0)
    mode 2 : write-through (C=1 B=0) - no write-allocate, reads still cached

and measures 600 KB fills with 32-bit and 64-bit stores for each mode, plus the
cache-clean cost.

Run from the project root:  python DSH/middleware/patch_fb_bench.py
"""
import io

PATH = "User/spine_test.cpp"
HEADER = "User/spine_test.h"
SELFTEST = "User/selftest.c"

CODE = r'''
/*----------------------------------------------------------------- 帧缓冲写带宽基准 + MPU 属性切换 */

#define FB_BW_BYTES (600u * 1024u)

extern "C" void fb_mpu_set(int mode)
{
    uint32_t attr = (3u << 24);                  /* AP = full access, XN = 0 */

    if (mode == 0)
    {
        attr |= (1u << 17) | (1u << 16);         /* write-back: C=1 B=1 */
    }
    else if (mode == 2)
    {
        attr |= (1u << 17);                      /* write-through: C=1 B=0 */
    }
    /* mode 1: non-cacheable, 无 C/B */

    HAL_MPU_Disable();
    MPU->RNR = 8u;
    MPU->RBAR = 0xC0000000u;
    MPU->RASR = (1u << 0) | (0x14u << 1) | attr; /* 2 MB */
    MPU->RNR = 9u;
    MPU->RBAR = 0xC1A00000u;
    MPU->RASR = (1u << 0) | (0x13u << 1) | attr; /* 1 MB */
    MPU->RNR = 10u;
    MPU->RBAR = 0xC1B00000u;
    MPU->RASR = (1u << 0) | (0x13u << 1) | attr; /* 1 MB */
    HAL_MPU_Enable(MPU_PRIVILEGED_DEFAULT);

    SCB_CleanInvalidateDCache();
}

static float fb_bw_fill32(void)
{
    volatile uint32_t *p = (volatile uint32_t *)FB_ADDR;
    uint32_t n = FB_BW_BYTES / 4u;
    uint32_t t0 = cyc_now();

    for (uint32_t i = 0; i < n; i++)
    {
        p[i] = 0x12345678u;
    }

    uint32_t c = cyc_now() - t0;
    SCB_CleanInvalidateDCache();
    return (float)c / 480000.0f;
}

static float fb_bw_fill64(void)
{
    volatile uint64_t *p = (volatile uint64_t *)FB_ADDR;
    uint32_t n = FB_BW_BYTES / 8u;
    uint32_t t0 = cyc_now();

    for (uint32_t i = 0; i < n; i++)
    {
        p[i] = 0x1234567812345678ull;
    }

    uint32_t c = cyc_now() - t0;
    SCB_CleanInvalidateDCache();
    return (float)c / 480000.0f;
}

static float fb_bw_clean(void)
{
    uint32_t t0 = cyc_now();

    SCB_CleanInvalidateDCache_by_Addr((uint32_t *)FB_ADDR, FB_BW_BYTES);

    return (float)(cyc_now() - t0) / 480000.0f;
}

extern "C" void fb_bench(void)
{
    const char *names[3] = { "write-back", "non-cacheable", "write-through" };

    printf("\r\n[FB] framebuffer write benchmark (600 KB)\r\n");

    for (int mode = 0; mode < 3; mode++)
    {
        fb_mpu_set(mode);

        float ms32 = fb_bw_fill32();
        float ms64 = fb_bw_fill64();
        float clean = fb_bw_clean();

        printf("[FB] %-13s 32bit %6.2f ms (%5.0f MB/s) | 64bit %6.2f ms (%5.0f MB/s) | clean %5.2f ms\r\n",
               names[mode], (double)ms32, (double)(600.0f / ms32), (double)ms64,
               (double)(600.0f / ms64), (double)clean);
    }

    fb_mpu_set(0);                               /* 恢复默认，供后续测试使用 */
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "fb_bench" in s:
        print("fb_bench already present")
        return

    marker = "/*----------------------------------------------------------------- 世界级重力 */"
    if marker not in s:
        raise SystemExit("anchor missing")

    s = s.replace(marker, CODE.strip() + "\n\n" + marker, 1)
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)

    h = io.open(HEADER, encoding="utf-8").read()
    if "fb_bench" not in h:
        h = h.replace("void  spine_world_set_gravity(float gx, float gy);",
                      "void  fb_bench(void);\nvoid  fb_mpu_set(int mode);\n\n"
                      "void  spine_world_set_gravity(float gx, float gy);")
        io.open(HEADER, "w", encoding="utf-8", newline="").write(h)

    c = io.open(SELFTEST, encoding="utf-8").read()
    old = "    /* 新素材：先打印动画列表并渲染总览 */"
    new = "    /* 帧缓冲写带宽基准（MPU 三种属性） */\n    fb_bench();\n\n    /* 新素材：先打印动画列表并渲染总览 */"
    if old in c and "fb_bench" not in c:
        c = c.replace(old, new, 1)
        io.open(SELFTEST, "w", encoding="utf-8", newline="").write(c)
        print("selftest wired")
    print("fb_bench added")


if __name__ == "__main__":
    main()
