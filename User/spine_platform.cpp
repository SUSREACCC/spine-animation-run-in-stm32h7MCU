/**
 ****************************************************************************************************
 * @file        spine_platform.cpp
 * @brief       spine-cpp 平台层实现：SDRAM first-fit 分配器 + getDefaultExtension() + FatFs 读文件
 * @note        为什么不用 C 库 malloc：栈/堆默认很小（Heap_Size=0），而 spine 解析一个骨架动辄
 *              几十到几百 KB。这里直接在 SDRAM 开 8 MB 池，自带分配器，完全绕开 C 库堆。
 ****************************************************************************************************
 */

#include <string.h>
#include <stdio.h>

#include "spine_platform.h"
#include "plat/plat.h"

extern "C"
{
#include "./SYSTEM/sys/sys.h"
#include "./FATFS/source/ff.h"
}

#include <spine/Atlas.h>
#include "./RASTER/raster2d.h"
#include <spine/Extension.h>
#include <spine/SpineString.h>

/*----------------------------------------------------------------- 简单 first-fit 分配器 */

namespace
{

struct Block
{
    uint32_t size;          /* 可用字节数（不含本头部） */
    Block   *next;
    Block   *prev;
    uint32_t free;
};

Block *g_head = nullptr;
Block *g_rover = nullptr;

uint32_t g_used = 0;
uint32_t g_peak = 0;
uint32_t g_allocs = 0;
uint32_t g_fails = 0;

const uint32_t HDR = (uint32_t)((sizeof(Block) + 7u) & ~7u);

static void *s_heap_base = nullptr;
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
    g_head->size = (uint32_t)(s_heap_size - HDR);
    g_head->next = nullptr;
    g_head->prev = nullptr;
    g_head->free = 1;
    g_rover = g_head;
}

static inline void *payload(Block *b)
{
    return (void *)((uint8_t *)b + HDR);
}

static inline Block *header_of(void *p)
{
    return (Block *)((uint8_t *)p - HDR);
}

void *heap_alloc(size_t n)
{
    plat_os_mem_lock();

    if (g_head == nullptr)
    {
        heap_init();
    }

    n = (n + 7u) & ~7u;

    if (n == 0)
    {
        n = 8;
    }

    /* next-fit：从漫游指针开始扫一圈，找不到再从头扫 */
    Block *start = (g_rover != nullptr) ? g_rover : g_head;

    for (int pass = 0; pass < 2; pass++)
    {
        for (Block *b = start; b != nullptr; b = b->next)
        {
            if ((b->free != 0u) && (b->size >= n))
            {
                if (b->size >= (n + HDR + 32u))
                {
                    Block *nb = (Block *)((uint8_t *)b + HDR + n);

                    nb->size = b->size - n - HDR;
                    nb->free = 1;
                    nb->next = b->next;
                    nb->prev = b;

                    if (b->next != nullptr)
                    {
                        b->next->prev = nb;
                    }
                    b->next = nb;
                    b->size = n;
                }

                b->free = 0;
                g_used += b->size + HDR;
                g_allocs++;
                g_rover = b;

                if (g_used > g_peak)
                {
                    g_peak = g_used;
                }
                plat_os_mem_unlock();
                return payload(b);
            }
        }

        start = g_head;                 /* 环绕一圈 */
    }

    g_fails++;
    plat_os_mem_unlock();
    return nullptr;
}

void heap_free(void *p)
{
    if (p == nullptr)
    {
        return;
    }

    plat_os_mem_lock();

    Block *b = header_of(p);

    if (b->free != 0u)
    {
        plat_os_mem_unlock();
        return;
    }

    b->free = 1;
    g_used -= (b->size + HDR);

    /* 与后邻合并 */
    if ((b->next != nullptr) && (b->next->free != 0u))
    {
        Block *n = b->next;

        b->size += HDR + n->size;
        b->next = n->next;

        if (n->next != nullptr)
        {
            n->next->prev = b;
        }
    }

    /* 与前邻合并（双向链表，O(1)） */
    if ((b->prev != nullptr) && (b->prev->free != 0u))
    {
        Block *q = b->prev;

        q->size += HDR + b->size;
        q->next = b->next;

        if (b->next != nullptr)
        {
            b->next->prev = q;
        }
        b = q;
    }

    g_rover = b;
    plat_os_mem_unlock();
}

void *heap_realloc(void *p, size_t n)
{
    if (p == nullptr)
    {
        return heap_alloc(n);
    }
    if (n == 0)
    {
        heap_free(p);
        return nullptr;
    }

    Block *b = header_of(p);

    if (b->size >= n)
    {
        return p;                       /* 原地够大，直接复用 */
    }

    void *np = heap_alloc(n);

    if (np == nullptr)
    {
        return nullptr;
    }

    memcpy(np, p, b->size);
    heap_free(p);
    return np;
}

/*----------------------------------------------------------------- Spine 扩展 */

class SpineMcuExtension : public spine::SpineExtension
{
public:
    SpineMcuExtension()
    {
        heap_init();
    }

    void *_alloc(size_t size, const char *file, int line) override
    {
        (void)file;
        (void)line;
        return heap_alloc(size);
    }

    void *_calloc(size_t size, const char *file, int line) override
    {
        (void)file;
        (void)line;

        void *p = heap_alloc(size);

        if (p != nullptr)
        {
            memset(p, 0, size);
        }
        return p;
    }

    void *_realloc(void *ptr, size_t size, const char *file, int line) override
    {
        (void)file;
        (void)line;
        return heap_realloc(ptr, size);
    }

    void _free(void *mem, const char *file, int line) override
    {
        (void)file;
        (void)line;
        heap_free(mem);
    }

    /** 从 SD 卡（FatFs）整体读入一个文件，语义与 spine 默认实现一致：返回 malloc 区，调用方负责 free */
    char *_readFile(const spine::String &path, int *length) override
    {
        char name[128];
        int  n = path.length();

        if ((length == nullptr) || (n <= 0) || (n >= (int)sizeof(name)))
        {
            return nullptr;
        }

        for (int i = 0; i < n; i++)
        {
            name[i] = path.buffer()[i];
        }
        name[n] = '\0';

        plat_file_t *pf = nullptr;

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
        }

        char *buf = (char *)heap_alloc((size_t)sz);

        if (buf == nullptr)
        {
            plat_file_close(pf);
            return nullptr;
        }

        {
            size_t got = 0;

            if ((plat_file_read(pf, buf, sz, &got) != 0) || (got != sz))
            {
                heap_free(buf);
                plat_file_close(pf);
                return nullptr;
            }
        }

        plat_file_close(pf);

        *length = (int)sz;
        return buf;
    }
};

/* 给惰性构造的 extension 用的静态存储（避免依赖堆/全局构造） */
struct BufferForExtension
{
    alignas(16) unsigned char bytes[sizeof(SpineMcuExtension)];
};

}  /* namespace */

/* 包装：把匿名 namespace 内的分配器暴露给其它模块 */
void *spine_heap_alloc(size_t n) { return heap_alloc(n); }
void  spine_heap_free(void *p) { heap_free(p); }

/* spine-cpp 要求由平台提供此函数 */
namespace spine
{
SpineExtension *getDefaultExtension()
{
    /* 必须惰性构造：SDRAM 控制器在 main() 里才初始化，
     * 若做成全局对象，其构造函数会在 SDRAM 就绪前写 0xC0200000 导致死机。 */
    static SpineMcuExtension *ext = nullptr;

    if (ext == nullptr)
    {
        static BufferForExtension storage;          /* 静态存储，无需堆 */
        ext = new (&storage) SpineMcuExtension();
        SpineExtension::setInstance(ext);
    }
    return ext;
}
}

extern "C" void spine_heap_get_stats(spine_heap_stats_t *st)
{
    if (st == nullptr)
    {
        return;
    }

    st->used_bytes = g_used;
    st->peak_bytes = g_peak;
    st->alloc_count = g_allocs;
    st->fail_count = g_fails;
}

extern "C" uint32_t spine_heap_block_count(void)
{
    uint32_t n = 0;

    for (Block *b = g_head; b != nullptr; b = b->next)
    {
        n++;
    }
    return n;
}

/*----------------------------------------------------------------- 资源区（bump 分配） */

static uint32_t s_arena_used = 0;

void *spine_arena_alloc(uint32_t bytes)
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

    void *p = (void *)((uint8_t *)s_arena_base + s_arena_used);

    s_arena_used += bytes;
    return p;
}

void spine_arena_reset(void)
{
    s_arena_used = 0;
}

uint32_t spine_arena_used(void)
{
    return s_arena_used;
}

/*----------------------------------------------------------------- 纹理加载 */

const RawTexture *spine_load_raw_texture(const char *raw_path)
{
    plat_file_t *pf = nullptr;
    uint8_t      hdr[16];
    size_t       got = 0;

    if (plat_file_open(&pf, raw_path) != 0)
    {
        const char *base = strrchr(raw_path, '/');

        if ((base == nullptr) || (plat_file_open(&pf, base + 1) != 0))
        {
            printf("[SPN] cannot open %s\r\n", raw_path);
            return nullptr;
        }
    }

    if ((plat_file_read(pf, hdr, 16, &got) != 0) || (got != 16) || (memcmp(hdr, "R2DT", 4) != 0))
    {
        plat_file_close(pf);
        printf("[SPN] bad header in %s\r\n", raw_path);
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
        printf("[SPN] unsupported raw texture %s (fmt=%u bytes=%lu)\r\n",
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
        printf("[SPN] arena full for %s (%lu bytes)\r\n", raw_path, (unsigned long)bytes);
        return nullptr;
    }

    if ((plat_file_read(pf, px, bytes, &got) != 0) || (got != bytes))
    {
        plat_file_close(pf);
        printf("[SPN] short read in %s\r\n", raw_path);
        return nullptr;
    }

    plat_file_close(pf);

    t->w = w;
    t->h = h;
    t->fmt = fmt;
    t->px = px;

    printf("[SPN] texture %s : %ux%u %s\r\n", raw_path, w, h,
           (fmt == 2u) ? "ARGB4444" : "ARGB1555");
    return t;
}

void RawTextureLoader::load(spine::AtlasPage &page, const spine::String &path)
{
    char raw[128];
    int  n = path.length();

    if ((n <= 0) || (n >= 120))
    {
        return;
    }

    const char *base = path.buffer();
    const char *slash = strrchr(base, '/');
    const char *name = slash ? (slash + 1) : base;

    snprintf(raw, sizeof(raw), "%s%s", TEXTURE_DIR, name);

    char *dot = strrchr(raw, '.');

    if (dot != nullptr)
    {
        strcpy(dot, ".raw");
    }

    const RawTexture *t = spine_load_raw_texture(raw);

    if (t == nullptr)
    {
        return;
    }

    page.texture = (void *)t;
    page.width = t->w;
    page.height = t->h;
}

void RawTextureLoader::unload(void *texture)
{
    (void)texture;
}

uint8_t spine_blend_of(spine::BlendMode m)
{
    switch (m)
    {
        case spine::BlendMode_Additive: return RASTER_BLEND_ADD;
        case spine::BlendMode_Multiply: return RASTER_BLEND_MULTIPLY;
        case spine::BlendMode_Screen:   return RASTER_BLEND_SCREEN;
        default:                        return RASTER_BLEND_NORMAL;
    }
}
