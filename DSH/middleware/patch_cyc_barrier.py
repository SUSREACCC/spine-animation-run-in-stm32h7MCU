#!/usr/bin/env python3
"""Fix the phase timers: the compiler is free to move ordinary calls across a
volatile read, so `draw_commands()` was being sunk past `DWT->CYCCNT`, making the
draw phase look 10x too fast and leaving the real cost unaccounted.

Adds cyc_now(), which issues a "memory" clobber before reading the cycle counter,
and uses it at every phase boundary in spine_play_duo.  Also fixes the phase-sum
expression, which overflowed uint32.

Run from the project root:  python DSH/middleware/patch_cyc_barrier.py
"""
import io

PATH = "User/spine_test.cpp"

HELPER = r'''
/* 计时用：内存屏障 + 读周期计数。
 * 只写 volatile 读不够——编译器仍可把普通函数调用挪到读之前/之后，
 * 实测导致 draw 段少算 10 倍。加 "memory" clobber 才能保证顺序。 */
static inline uint32_t cyc_now(void)
{
    __asm volatile("" ::: "memory");
    return DWT->CYCCNT;
}

'''


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "cyc_now" in s:
        print("already patched")
        return

    anchor = "/*----------------------------------------------------------------- 双角色 + 反复重载 */"
    if anchor not in s:
        raise SystemExit("duo anchor not found")
    s = s.replace(anchor, HELPER.strip() + "\n\n" + anchor, 1)

    # 该函数体（duo）里的所有计时点改用 cyc_now()
    start = s.index("extern \"C\" uint8_t spine_play_duo(")
    head, tail = s[:start], s[start:]

    for a, b in (
        ("uint32_t fr0 = DWT->CYCCNT;", "uint32_t fr0 = cyc_now();"),
        ("uint32_t p1 = DWT->CYCCNT;", "uint32_t p1 = cyc_now();"),
        ("uint32_t p2 = DWT->CYCCNT;", "uint32_t p2 = cyc_now();"),
        ("uint32_t c0 = DWT->CYCCNT;", "uint32_t c0 = cyc_now();"),
        ("uint32_t c1 = DWT->CYCCNT;", "uint32_t c1 = cyc_now();"),
        ("uint32_t c2 = DWT->CYCCNT;", "uint32_t c2 = cyc_now();"),
        ("uint32_t w0 = DWT->CYCCNT;", "uint32_t w0 = cyc_now();"),
        ("wait_cyc += DWT->CYCCNT - w0;", "wait_cyc += cyc_now() - w0;"),
        ("pre_cyc += DWT->CYCCNT - c2;", "pre_cyc += cyc_now() - c2;"),
        ("frame_cyc_sum += (uint32_t)(DWT->CYCCNT - fr0);", "frame_cyc_sum += (uint32_t)(cyc_now() - fr0);"),
    ):
        tail = tail.replace(a, b)

    # 修 sum 的 uint32 溢出：逐项转 double 再相加
    old_sum = "(double)((float)(anim_cyc + build_cyc + clr_cyc + ras_cyc + pre_cyc + wait_cyc) / 480000.0f / (float)total_frames)"
    new_sum = ("((double)anim_cyc + (double)build_cyc + (double)clr_cyc + (double)ras_cyc\n"
               "                + (double)pre_cyc + (double)wait_cyc) / 480000.0 / (double)total_frames")
    tail = tail.replace(old_sum, new_sum)

    s = head + tail
    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("cyc_now barrier installed and phase sum fixed")


if __name__ == "__main__":
    main()
