#!/usr/bin/env python3
"""Teach the target side about both texture formats (ARGB1555 and ARGB4444):

  * RawTexture carries the format read from the .raw header
  * load_raw_texture accepts format id 1 or 2
  * draw_commands picks the matching raster_format_t instead of hard-coding 1555

Run from the project root:  python DSH/middleware/patch_spine_fmt4444.py
"""
import io

PATH = "User/spine_test.cpp"


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "tex->fmt" in s:
        print("already patched")
        return

    # --- 1) RawTexture 增加 fmt ---
    old_struct = """struct RawTexture
{
    uint16_t        w;
    uint16_t        h;
    const uint16_t *px;
};"""
    new_struct = """struct RawTexture
{
    uint16_t        w;
    uint16_t        h;
    uint16_t        fmt;        /* 1 = ARGB1555, 2 = ARGB4444（来自 .raw 文件头） */
    const uint16_t *px;
};"""
    if old_struct not in s:
        raise SystemExit("RawTexture struct not found")
    s = s.replace(old_struct, new_struct, 1)

    # --- 2) 加载器接受两种格式 ---
    old_check = """    if ((fmt != 1u) || (bytes != (uint32_t)w * h * 2u))
    {
        f_close(&fil);
        printf("[SPN] unsupported raw texture %s (fmt=%u bytes=%lu)\\r\\n", raw_path, fmt, (unsigned long)bytes);
        return nullptr;
    }"""
    new_check = """    if (((fmt != 1u) && (fmt != 2u)) || (bytes != (uint32_t)w * h * 2u))
    {
        f_close(&fil);
        printf("[SPN] unsupported raw texture %s (fmt=%u bytes=%lu)\\r\\n", raw_path, fmt, (unsigned long)bytes);
        return nullptr;
    }"""
    if old_check not in s:
        raise SystemExit("format check not found")
    s = s.replace(old_check, new_check, 1)

    old_assign = """    t->w = w;
    t->h = h;
    t->px = px;

    printf("[SPN] texture %s : %ux%u ARGB1555\\r\\n", raw_path, w, h);
    return t;"""
    new_assign = """    t->w = w;
    t->h = h;
    t->fmt = fmt;
    t->px = px;

    printf("[SPN] texture %s : %ux%u %s\\r\\n", raw_path, w, h,
           (fmt == 2u) ? "ARGB4444" : "ARGB1555");
    return t;"""
    if old_assign not in s:
        raise SystemExit("texture assign not found")
    s = s.replace(old_assign, new_assign, 1)

    # --- 3) 渲染时按纹理实际格式分派 ---
    old_fmt = """            rt.fmt = RASTER_FMT_ARGB1555;
            rt.key = 0;"""
    new_fmt = """            rt.fmt = (tex->fmt == 2u) ? RASTER_FMT_ARGB4444 : RASTER_FMT_ARGB1555;
            rt.key = 0;"""
    if old_fmt not in s:
        raise SystemExit("rt.fmt assignment not found")
    s = s.replace(old_fmt, new_fmt, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("ARGB4444 support wired into the loader and renderer")


if __name__ == "__main__":
    main()
