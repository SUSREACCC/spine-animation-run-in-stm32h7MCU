#!/usr/bin/env python3
"""Replace the spine heap allocator with a doubly-linked + rover version.

The old one did a first-fit scan from the head on every alloc and a full scan
from the head on every free to find the predecessor.  Parsing spineboy creates
~7000 blocks, turning the parse into O(n^2): measured 7.2 s for a 65 KB skeleton.

New:
  * blocks are doubly linked -> coalescing on free is O(1)
  * allocation starts from a rover (next-fit) instead of the head

Run from the project root:  python DSH/middleware/patch_spine_allocator.py
"""
import io

PATH = "User/spine_platform.cpp"

NEW_ALLOC = r'''struct Block
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

void heap_init()
{
    g_head = (Block *)SPINE_HEAP_BASE;
    g_head->size = SPINE_HEAP_SIZE - HDR;
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
                return payload(b);
            }
        }

        start = g_head;                 /* 环绕一圈 */
    }

    g_fails++;
    return nullptr;
}

void heap_free(void *p)
{
    if (p == nullptr)
    {
        return;
    }

    Block *b = header_of(p);

    if (b->free != 0u)
    {
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
'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "g_rover" in s:
        print("allocator already upgraded")
        return

    start = s.find("struct Block")
    end = s.find("/*----------------------------------------------------------------- Spine 扩展 */")

    if start < 0 or end < 0:
        raise SystemExit("allocator block not found")

    s = s[:start] + NEW_ALLOC + "\n" + s[end:]

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("allocator replaced (doubly linked + rover)")


if __name__ == "__main__":
    main()
