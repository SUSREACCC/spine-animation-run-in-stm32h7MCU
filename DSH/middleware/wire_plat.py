#!/usr/bin/env python3
"""Wire the library to the platform abstraction layer (plat.h).

  spine_platform.cpp : heap pools, arena, file I/O  -> plat_mem_pools / plat_file_*
  spine_api.cpp      : framebuffer, present, cache  -> plat_fb_* / plat_fb_need_cache_clean
  raster2d.cpp       : raster_flush                 -> plat_cache_clean
  spine_test.cpp     : ltdc helper + fb_mpu_set     -> plat_fb_present / plat_fb_set_cache_mode

Behaviour must be identical; verify with a build + one boot.

Run from the project root:  python DSH/middleware/wire_plat.py
"""
import io

PS = "User/spine_platform.cpp"
API = "User/spine_api.cpp"
R2D = "Middlewares/RASTER/raster2d.cpp"
TEST = "User/spine_test.cpp"


def patch_platform():
    s = io.open(PS, encoding="utf-8").read()

    if 'plat_mem_pools' in s:
        print("platform: already wired")
        return

    # 1) heap_init 用平台提供的内存池
    old = """void heap_init()
{
    /* 幂等：SpineMcuExtension 是惰性构造的，它的构造函数也会调用 heap_init。
     * 若此时堆已经被用过（例如 API 层先分配了 asset 结构体），重置会丢弃
     * 已有分配并导致两块内存重叠。 */
    if (g_head != nullptr)
    {
        return;
    }

    g_head = (Block *)SPINE_HEAP_BASE;
    g_head->size = SPINE_HEAP_SIZE - HDR;"""
    new = """static void *s_heap_base = nullptr;
static size_t s_heap_size = 0;
static void *s_arena_base = nullptr;
static size_t s_arena_size = 0;

void heap_init()
{
    /* 幂等：SpineMcuExtension 是惰性构造的，它的构造函数也会调用 heap_init。
     * 若此时堆已经被用过（例如 API 层先分配了 asset 结构体），重置会丢弃
     * 已有分配并导致两块内存重叠。 */
    if (g_head != nullptr)
    {
        return;
    }

    /* 内存由平台层提供（plat_mem_pools），库内不含任何绝对地址 */
    if (s_heap_base == nullptr)
    {
        plat_mem_pools(&s_heap_base, &s_heap_size, &s_arena_base, &s_arena_size);
    }

    g_head = (Block *)s_heap_base;
    g_head->size = (uint32_t)(s_heap_size - HDR);"""
    assert old in s, "heap_init block not found"
    s = s.replace(old, new, 1)

    # 2) arena 用平台提供的内存
    old2 = """void *spine_arena_alloc(uint32_t bytes)
{
    bytes = (bytes + 3u) & ~3u;

    if ((s_arena_used + bytes) > SPINE_ARENA_SIZE)
    {
        return nullptr;
    }

    void *p = (void *)(SPINE_ARENA_BASE + s_arena_used);"""
    new2 = """void *spine_arena_alloc(uint32_t bytes)
{
    bytes = (bytes + 3u) & ~3u;

    if (s_arena_base == nullptr)
    {
        plat_mem_pools(&s_heap_base, &s_heap_size, &s_arena_base, &s_arena_size);
    }

    if ((s_arena_used + bytes) > s_arena_size)
    {
        return nullptr;
    }

    void *p = (void *)((uint8_t *)s_arena_base + s_arena_used);"""
    assert old2 in s, "arena alloc block not found"
    s = s.replace(old2, new2, 1)

    # 3) 文件读：_readFile 换成 plat_file_*
    old3 = """        if (f_open(&fil, name, FA_READ) != FR_OK)
        {
            /* 回退：文件若放在卡根目录（而不是 /spine/ 下），用 basename 再试一次 */
            const char *base = strrchr(name, '/');

            if ((base == nullptr) || (f_open(&fil, base + 1, FA_READ) != FR_OK))
            {
                return nullptr;
            }
        }

        FSIZE_t sz = f_size(&fil);

        if ((sz == 0) || (sz > (FSIZE_t)(4 * 1024 * 1024)))
        {
            f_close(&fil);
            return nullptr;
        }"""
    new3 = """        plat_file_t *pf = nullptr;

        if (plat_file_open(&pf, name) != 0)
        {
            /* 回退：文件若放在卡根目录（而不是 /spine/ 下），用 basename 再试一次 */
            const char *base = strrchr(name, '/');

            if ((base == nullptr) || (plat_file_open(&pf, base + 1) != 0))
            {
                return nullptr;
            }
        }

        size_t sz = 0;

        plat_file_size(pf, &sz);

        if ((sz == 0) || (sz > (size_t)(4 * 1024 * 1024)))
        {
            plat_file_close(pf);
            return nullptr;
        }"""
    assert old3 in s, "_readFile open block not found"
    s = s.replace(old3, new3, 1)

    io.open(PS, "w", encoding="utf-8", newline="").write(s)
    print("platform: heap/arena/file wired")


def patch_platform_io_rest():
    """Replace the remaining f_read / f_close inside _readFile and the raw texture loader."""
    s = io.open(PS, encoding="utf-8").read()

    # _readFile 的读取与关闭
    old = """        if (f_read(&fil, buf, (UINT)sz, &br) != FR_OK)
        {
            f_close(&fil);
            heap_free(buf);
            return nullptr;
        }

        f_close(&fil);"""
    new = """        {
            size_t got = 0;

            if ((plat_file_read(pf, buf, sz, &got) != 0) || (got != sz))
            {
                plat_file_close(pf);
                heap_free(buf);
                return nullptr;
            }
        }

        plat_file_close(pf);"""
    if old in s:
        s = s.replace(old, new, 1)
        print("platform: _readFile read/close wired")

    io.open(PS, "w", encoding="utf-8", newline="").write(s)


def patch_raw_texture():
    s = io.open(PS, encoding="utf-8").read()

    old_start = s.find("const RawTexture *spine_load_raw_texture(const char *raw_path)")
    if old_start < 0:
        print("raw texture loader not found")
        return

    end = s.find("\nvoid RawTextureLoader::load", old_start)
    if end < 0:
        print("raw loader end not found")
        return

    body = s[old_start:end]

    if "plat_file_open" in body:
        print("raw texture loader already wired")
        return

    new_body = '''const RawTexture *spine_load_raw_texture(const char *raw_path)
{
    plat_file_t *pf = nullptr;
    uint8_t      hdr[16];
    size_t       got = 0;

    if (plat_file_open(&pf, raw_path) != 0)
    {
        const char *base = strrchr(raw_path, '/');

        if ((base == nullptr) || (plat_file_open(&pf, base + 1) != 0))
        {
            printf("[SPN] cannot open %s\\r\\n", raw_path);
            return nullptr;
        }
    }

    if ((plat_file_read(pf, hdr, 16, &got) != 0) || (got != 16) || (memcmp(hdr, "R2DT", 4) != 0))
    {
        plat_file_close(pf);
        printf("[SPN] bad header in %s\\r\\n", raw_path);
        return nullptr;
    }

    uint16_t w     = (uint16_t)(hdr[4] | (hdr[5] << 8));
    uint16_t h     = (uint16_t)(hdr[6] | (hdr[7] << 8));
    uint16_t fmt   = (uint16_t)(hdr[8] | (hdr[9] << 8));
    uint32_t bytes = (uint32_t)hdr[12] | ((uint32_t)hdr[13] << 8) |
                     ((uint32_t)hdr[14] << 16) | ((uint32_t)hdr[15] << 24);

    if (((fmt != 1u) && (fmt != 2u)) || (bytes != (uint32_t)w * h * 2u) ||
        (w > PLAT_TEXTURE_MAX_W) || (h > PLAT_TEXTURE_MAX_H))
    {
        plat_file_close(pf);
        printf("[SPN] unsupported raw texture %s (fmt=%u bytes=%lu)\\r\\n",
               raw_path, fmt, (unsigned long)bytes);
        return nullptr;
    }

    RawTexture *t = (RawTexture *)spine_arena_alloc(sizeof(RawTexture));

    if (t == nullptr)
    {
        plat_file_close(pf);
        return nullptr;
    }

    uint16_t *px = (uint16_t *)spine_arena_alloc(bytes);

    if (px == nullptr)
    {
        plat_file_close(pf);
        printf("[SPN] arena full for %s (%lu bytes)\\r\\n", raw_path, (unsigned long)bytes);
        return nullptr;
    }

    if ((plat_file_read(pf, px, bytes, &got) != 0) || (got != bytes))
    {
        plat_file_close(pf);
        printf("[SPN] short read in %s\\r\\n", raw_path);
        return nullptr;
    }

    plat_file_close(pf);

    t->w = w;
    t->h = h;
    t->fmt = fmt;
    t->px = px;

    printf("[SPN] texture %s : %ux%u %s\\r\\n", raw_path, w, h,
           (fmt == 2u) ? "ARGB4444" : "ARGB1555");
    return t;
}
'''

    s = s[:old_start] + new_body + s[end:]
    io.open(PS, "w", encoding="utf-8", newline="").write(s)
    print("platform: raw texture loader wired to plat_file_*")


def patch_api():
    s = io.open(API, encoding="utf-8").read()

    if "plat_fb_addr" in s:
        print("api: already wired")
        return

    # 帧缓冲地址来自平台层
    s = s.replace("""    g_d.bufs[0] = SPINE_FB0;
    g_d.bufs[1] = SPINE_FB1;
    g_d.bufs[2] = SPINE_FB2;""",
"""    for (int i = 0; i < 3; i++)
    {
        g_d.bufs[i] = (uint16_t *)plat_fb_addr(i);
    }""")

    # present 走平台
    s = s.replace("""static void api_set_framebuffer(uint16_t *addr)
{
    LTDC_Layer1->CFBAR = (uint32_t)addr;
    LTDC->SRCR = LTDC_SRCR_VBR;
}""",
"""static void api_set_framebuffer(uint16_t *addr)
{
    plat_fb_present(addr);
}""")

    # 缓存冲刷判断走平台
    s = s.replace("extern int g_fb_write_through;", "")
    s = s.replace("if (!g_fb_write_through)", "if (plat_fb_need_cache_clean())")

    # 结尾的 VBR 忙等交给 plat_fb_present
    s = s.replace("""    while ((LTDC->SRCR & LTDC_SRCR_VBR) != 0u)
    {
    }

    api_set_framebuffer(dst);""",
"""    api_set_framebuffer(dst);""")

    io.open(API, "w", encoding="utf-8", newline="").write(s)
    print("api: framebuffer/present/cache wired")


def patch_raster():
    s = io.open(R2D, encoding="utf-8").read()

    if "plat_cache_clean" in s:
        print("raster2d: already wired")
        return

    start = s.find('extern "C" void raster_flush(uint16_t *fb, int bytes)')
    if start < 0:
        print("raster_flush not found")
        return

    end = s.find("\n}", start)
    new_body = '''extern "C" void raster_flush(uint16_t *fb, int bytes)
{
    /* 交给平台层：H743 上是 SCB_CleanInvalidateDCache_by_Addr，
     * 无 D-Cache 的平台可以为空实现。 */
    plat_cache_clean(fb, (size_t)bytes);
}'''
    s = s[:start] + new_body + s[end + 2:]
    s = s.replace('#include "raster2d.h"', '#include "raster2d.h"\n#include "plat/plat.h"', 1)
    io.open(R2D, "w", encoding="utf-8", newline="").write(s)
    print("raster2d: raster_flush wired to plat_cache_clean")


def patch_test():
    s = io.open(TEST, encoding="utf-8").read()

    if "plat_fb_set_cache_mode" in s:
        print("test: already wired")
        return

    # fb_mpu_set -> 平台
    start = s.find('extern "C" void fb_mpu_set(int mode)')
    if start > 0:
        end = s.find("\n}\n", start)
        s = s[:start] + '''extern "C" void fb_mpu_set(int mode)
{
    plat_fb_set_cache_mode(mode);       /* 帧缓冲缓存属性由平台层管理 */
    g_fb_write_through = (mode == 2);
}
''' + s[end + 3:]
        print("test: fb_mpu_set -> plat_fb_set_cache_mode")

    io.open(TEST, "w", encoding="utf-8", newline="").write(s)


def main():
    patch_platform()
    patch_platform_io_rest()
    patch_raw_texture()
    patch_api()
    patch_raster()
    patch_test()


if __name__ == "__main__":
    main()
