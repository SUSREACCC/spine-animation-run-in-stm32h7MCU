#!/usr/bin/env python3
"""Split the skeleton load into "read file" vs "parse", and report the allocator
block count, to locate the 7.3 s load time.

Run from the project root:  python DSH/middleware/patch_spine_loadprof.py
"""
import io

PATH = "User/spine_test.cpp"
PLATFORM = "User/spine_platform.cpp"
PLATFORM_H = "User/spine_platform.h"


def main():
    # --- 统计分配器块数 ---
    h = io.open(PLATFORM_H, encoding="utf-8").read()
    if "spine_heap_block_count" not in h:
        h = h.replace("void spine_heap_get_stats(spine_heap_stats_t *st);",
                      "void spine_heap_get_stats(spine_heap_stats_t *st);\n\n"
                      "/* 分配器当前链表块数（用于诊断碎片化） */\n"
                      "uint32_t spine_heap_block_count(void);")
        io.open(PLATFORM_H, "w", encoding="utf-8", newline="").write(h)

    p = io.open(PLATFORM, encoding="utf-8").read()
    if "spine_heap_block_count" not in p:
        p = p.rstrip() + """

extern "C" uint32_t spine_heap_block_count(void)
{
    uint32_t n = 0;

    for (Block *b = g_head; b != nullptr; b = b->next)
    {
        n++;
    }
    return n;
}
"""
        io.open(PLATFORM, "w", encoding="utf-8", newline="").write(p)

    # --- 拆分 read / parse ---
    s = io.open(PATH, encoding="utf-8").read()

    old = """        spine::AtlasAttachmentLoader attachment_loader(atlas);
        spine::SkeletonBinary        binary(attachment_loader, false);
        spine::SkeletonData         *sd = binary.readSkeletonDataFile(skel_path);"""
    new = """        spine::AtlasAttachmentLoader attachment_loader(atlas);
        spine::SkeletonBinary        binary(attachment_loader, false);

        uint32_t t_r0 = DWT->CYCCNT;
        int      bin_len = 0;
        char    *bin = spine::SpineExtension::readFile(spine::String(skel_path), &bin_len);
        uint32_t t_r1 = DWT->CYCCNT;

        spine::SkeletonData *sd = (bin != nullptr)
                                  ? binary.readSkeletonData((const unsigned char *)bin, bin_len)
                                  : nullptr;
        uint32_t t_r2 = DWT->CYCCNT;

        if (bin != nullptr)
        {
            spine::SpineExtension::free(bin, __FILE__, __LINE__);
        }"""
    if old not in s:
        raise SystemExit("load block not found")
    s = s.replace(old, new, 1)

    old_print = '        printf("[DUO] it%d load %.1f ms (tex %.1f + skel %.1f) |'
    new_print = '        printf("[DUO] it%d load %.1f ms (tex %.1f + read %.1f + parse %.1f, blocks %lu) |'
    if old_print not in s:
        raise SystemExit("print not found")
    s = s.replace(old_print, new_print, 1)

    old_args = """               it + 1, load_ms,
               (float)(t_tex1 - t_tex0) / 480000.0f,
               load_ms - (float)(t_tex1 - t_tex0) / 480000.0f,
               frame_ms, 1000.0f / frame_ms,"""
    new_args = """               it + 1, load_ms,
               (float)(t_tex1 - t_tex0) / 480000.0f,
               (float)(t_r1 - t_r0) / 480000.0f,
               (float)(t_r2 - t_r1) / 480000.0f,
               (unsigned long)spine_heap_block_count(),
               frame_ms, 1000.0f / frame_ms,"""
    if old_args not in s:
        raise SystemExit("print args not found")
    s = s.replace(old_args, new_args, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("load profiling installed")


if __name__ == "__main__":
    main()
