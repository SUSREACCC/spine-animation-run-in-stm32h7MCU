#!/usr/bin/env python3
"""Step 1 of API normalisation: move the platform-ish helpers to spine_platform.

    RawTexture / load_raw_texture / RawTextureLoader / blend_of / arena_alloc
        spine_test.cpp  ->  spine_platform.cpp + spine_platform.h (C++ section)

Needed so a new API module can reuse texture loading and the arena without
depending on the test harness.  Behaviour must stay identical; verify with a
build + one boot.

Run from the project root:  python DSH/middleware/move_texture_layer.py
"""
import io

TEST = "User/spine_test.cpp"
PLAT_H = "User/spine_platform.h"
PLAT_CPP = "User/spine_platform.cpp"

H_ADD = r'''
#ifdef __cplusplus

#include <spine/TextureLoader.h>
#include <spine/BlendMode.h>

#define TEXTURE_DIR "/spine/"

/* 原始纹理（png_to_raw.py 生成，16 字节头 + ARGB1555/4444 像素） */
struct RawTexture
{
    uint16_t        w;
    uint16_t        h;
    uint16_t        fmt;        /* 1 = ARGB1555, 2 = ARGB4444 */
    const uint16_t *px;
};

/* 资源区（bump 分配）：纹理、顶点缓冲等生命周期 = 一次加载 */
void    *spine_arena_alloc(uint32_t bytes);
void     spine_arena_reset(void);
uint32_t spine_arena_used(void);

const RawTexture *spine_load_raw_texture(const char *raw_path);

class RawTextureLoader : public spine::TextureLoader
{
public:
    void load(spine::AtlasPage &page, const spine::String &path) override;
    void unload(void *texture) override;
};

/* spine 混合模式 -> raster2d 混合模式 */
uint8_t spine_blend_of(spine::BlendMode m);

#endif /* __cplusplus */
'''

CPP_ADD = r'''
/*----------------------------------------------------------------- 资源区（bump 分配） */

static uint32_t s_arena_used = 0;

void *spine_arena_alloc(uint32_t bytes)
{
    bytes = (bytes + 3u) & ~3u;

    if ((s_arena_used + bytes) > SPINE_ARENA_SIZE)
    {
        return nullptr;
    }

    void *p = (void *)(SPINE_ARENA_BASE + s_arena_used);

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
    FIL     fil;
    UINT    br = 0;
    uint8_t hdr[16];

    if ((f_open(&fil, raw_path, FA_READ) != FR_OK) &&
        ((strrchr(raw_path, '/') == nullptr) ||
         (f_open(&fil, strrchr(raw_path, '/') + 1, FA_READ) != FR_OK)))
    {
        printf("[SPN] cannot open %s\r\n", raw_path);
        return nullptr;
    }

    if ((f_read(&fil, hdr, 16, &br) != FR_OK) || (br != 16) || (memcmp(hdr, "R2DT", 4) != 0))
    {
        f_close(&fil);
        printf("[SPN] bad header in %s\r\n", raw_path);
        return nullptr;
    }

    uint16_t w     = (uint16_t)(hdr[4] | (hdr[5] << 8));
    uint16_t h     = (uint16_t)(hdr[6] | (hdr[7] << 8));
    uint16_t fmt   = (uint16_t)(hdr[8] | (hdr[9] << 8));
    uint32_t bytes = (uint32_t)hdr[12] | ((uint32_t)hdr[13] << 8) |
                     ((uint32_t)hdr[14] << 16) | ((uint32_t)hdr[15] << 24);

    if (((fmt != 1u) && (fmt != 2u)) || (bytes != (uint32_t)w * h * 2u))
    {
        f_close(&fil);
        printf("[SPN] unsupported raw texture %s (fmt=%u bytes=%lu)\r\n",
               raw_path, fmt, (unsigned long)bytes);
        return nullptr;
    }

    RawTexture *t = (RawTexture *)spine_arena_alloc(sizeof(RawTexture));

    if (t == nullptr)
    {
        f_close(&fil);
        return nullptr;
    }

    uint16_t *px = (uint16_t *)spine_arena_alloc(bytes);

    if (px == nullptr)
    {
        f_close(&fil);
        printf("[SPN] arena full for %s (%lu bytes)\r\n", raw_path, (unsigned long)bytes);
        return nullptr;
    }

    if ((f_read(&fil, px, bytes, &br) != FR_OK) || (br != bytes))
    {
        f_close(&fil);
        printf("[SPN] short read in %s\r\n", raw_path);
        return nullptr;
    }

    f_close(&fil);

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
'''


def patch_header():
    h = io.open(PLAT_H, encoding="utf-8").read()

    if "spine_arena_alloc" in h:
        print("header: already patched")
        return

    h = h.replace("#ifdef __cplusplus\n}\n#endif\n\n#endif",
                  "#ifdef __cplusplus\n}\n#endif\n" + H_ADD + "\n#endif")
    io.open(PLAT_H, "w", encoding="utf-8", newline="").write(h)
    print("header: patched")


def patch_cpp():
    p = io.open(PLAT_CPP, encoding="utf-8").read()

    if "spine_load_raw_texture" in p:
        print("cpp: already patched")
        return

    p = p.rstrip() + "\n" + CPP_ADD
    io.open(PLAT_CPP, "w", encoding="utf-8", newline="").write(p)
    print("cpp: patched")


def strip_test_file():
    """Remove the moved definitions from spine_test.cpp and switch to the
    platform names."""
    lines = io.open(TEST, encoding="utf-8").read().split("\n")
    out = []
    i = 0
    removed = 0

    while i < len(lines):
        ln = lines[i]

        # 1) struct RawTexture
        if ln.startswith("struct RawTexture"):
            while i < len(lines) and lines[i].strip() != "};":
                i += 1
            i += 1
            removed += 1
            continue

        # 2) arena_alloc + s_arena_used
        if ln.startswith("static uint32_t s_arena_used"):
            i += 1
            removed += 1
            continue

        if ln.startswith("static uint16_t *arena_alloc("):
            while i < len(lines) and lines[i].strip() != "}":
                i += 1
            i += 1
            continue

        # 3) load_raw_texture
        if ln.startswith("static const RawTexture *load_raw_texture("):
            while i < len(lines) and lines[i].strip() != "}":
                i += 1
            i += 1
            removed += 1
            continue

        # 4) RawTextureLoader 类
        if ln.startswith("class RawTextureLoader"):
            while i < len(lines) and lines[i].strip() != "};":
                i += 1
            i += 1
            removed += 1
            continue

        # 5) blend_of
        if ln.startswith("static inline uint8_t blend_of("):
            while i < len(lines) and lines[i].strip() != "}":
                i += 1
            i += 1
            removed += 1
            continue

        out.append(ln)
        i += 1

    s = "\n".join(out)
    s = s.replace("arena_alloc(", "spine_arena_alloc(")
    s = s.replace("spine_spine_arena_alloc(", "spine_arena_alloc(")
    s = s.replace("s_arena_used = 0;", "spine_arena_reset();")
    s = s.replace("(unsigned long)s_arena_used", "(unsigned long)spine_arena_used()")
    s = s.replace("blend_of(cmd->blendMode)", "spine_blend_of(cmd->blendMode)")

    io.open(TEST, "w", encoding="utf-8", newline="").write(s)
    print("test file stripped, blocks removed:", removed)


def main():
    patch_header()
    patch_cpp()
    strip_test_file()


if __name__ == "__main__":
    main()
