#!/usr/bin/env python3
"""Rewrite raster_upscale2x for the framebuffer's actual write ceiling.

Measurements (600 KB fill into the framebuffer):
    32-bit stores : 144 MB/s (4.16 ms)
    64-bit stores : 170 MB/s (3.52 ms)   <-- ceiling
    cache clean   : 0.28 ms

present currently runs at ~72 MB/s (8.30 ms for ~600 KB), i.e. 2.4x off the
ceiling.  Two causes:

  1. the old loop wrote source row y to destination rows 2y and 2y+1 in the same
     inner iteration -> two interleaved write streams, SDRAM row thrash;
  2. 32-bit stores only.

New version walks the DESTINATION rows in order (single sequential stream) and
packs two source pixels into one 64-bit store (4 output pixels), with a 32-bit
prologue when the destination is not 8-byte aligned and a 32-bit epilogue for an
odd pixel count.

Run from the project root:  python DSH/middleware/patch_upscale_fast.py
"""
import io

PATH = "Middlewares/RASTER/raster2d.cpp"

NEW = r'''extern "C" void raster_upscale2x(const uint16_t *src, int src_stride,
                                 uint16_t *dst, int dst_stride,
                                 int sx0, int sy0, int sx1, int sy1)
{
    int n = sx1 - sx0 + 1;

    if (n <= 0)
    {
        return;
    }

    /* 按"目标行"顺序写：每一行写完再写下一行，形成单条顺序写流。
     * 源行每个被读两次（r 和 r+1 对应同一源行），但源缓冲可 cache。 */
    for (int r = 2 * sy0; r <= 2 * sy1 + 1; r++)
    {
        const uint16_t *s = src + (size_t)(r >> 1) * src_stride + sx0;
        uint8_t        *dp = (uint8_t *)(dst + (size_t)r * dst_stride + 2 * sx0);
        int             i = 0;

        /* 8 字节对齐前缀（sx0 为奇数时 1 个源像素） */
        if ((((uintptr_t)dp) & 7u) != 0u)
        {
            uint16_t v = s[0];
            uint32_t vv = ((uint32_t)v << 16) | (uint32_t)v;

            *(uint32_t *)dp = vv;
            dp += 4;
            i = 1;

            if (i >= n)
            {
                continue;
            }
        }

        /* 主体：2 个源像素 -> 4 个输出像素 = 一次 64 位写 */
        int pairs = (n - i) >> 1;

        for (int k = 0; k < pairs; k++)
        {
            uint16_t a = s[i];
            uint16_t b = s[i + 1];
            uint64_t packed = ((uint64_t)a << 48) | ((uint64_t)a << 32)
                            | ((uint64_t)b << 16) | (uint64_t)b;

            *(uint64_t *)dp = packed;
            dp += 8;
            i += 2;
        }

        /* 尾像素（n 为奇数时） */
        if (i < n)
        {
            uint16_t v = s[i];
            uint32_t vv = ((uint32_t)v << 16) | (uint32_t)v;

            *(uint32_t *)dp = vv;
        }
    }
}
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "单条顺序写流" in s:
        print("upscale already optimized")
        return

    start = s.find("extern \"C\" void raster_upscale2x(")
    if start < 0:
        raise SystemExit("upscale not found")

    s = s[:start] + NEW
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("raster_upscale2x rewritten (row-ordered + 64-bit)")


if __name__ == "__main__":
    main()
