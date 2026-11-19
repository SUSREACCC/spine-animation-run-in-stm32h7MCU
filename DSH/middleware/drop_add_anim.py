#!/usr/bin/env python3
"""Drop add_anim from the public API.

On hardware the queued animation DOES take over inside spine (`setTrack(i, next)`),
but the takeover detaches the old TrackEntry from the `next` chain, so our cached
pointer can no longer see it: current_anim()/get_time() would keep reporting the
previous animation (its time freezes at the switch point).  Without a public
"get current entry for track" accessor there is no clean way to follow it, so the
honest move is to not ship it.

Kept (all verified on hardware):
  set_default_mix / set_mix / get_time / current_anim / seek

Run from the project root:  python DSH/middleware/drop_add_anim.py
"""
import io

H = "User/spine_api.h"
CPP = "User/spine_api.cpp"
TEST = "User/spine_anim_test.c"

H_DECL = """/** 排队下一段动画（当前段结束后按 delay 秒开始）。返回 1 = 成功 */
int spine_instance_add_anim(spine_instance_t *in, const char *anim, int loop, float delay, int track);
"""

CPP_FN_START = "int spine_instance_add_anim(spine_instance_t *in, const char *anim, int loop, float delay, int track)"


def main():
    h = io.open(H, encoding="utf-8").read()

    if H_DECL in h:
        h = h.replace(H_DECL, "")
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: add_anim declaration removed")

    s = io.open(CPP, encoding="utf-8").read()
    i = s.find(CPP_FN_START)

    if i >= 0:
        j = s.find("\n}\n", i)
        assert j > i
        s = s[:i] + s[j + 3:]
        io.open(CPP, "w", encoding="utf-8", newline="").write(s)
        print("cpp: add_anim implementation removed")

    t = io.open(TEST, encoding="utf-8").read()
    start = t.find("    /* ---- 5. 排队下一段")
    end = t.find('    printf(ANT_TAG "RESULT %s')

    if (start > 0) and (end > start):
        t = t[:start] + t[end:]
        io.open(TEST, "w", encoding="utf-8", newline="").write(t)
        print("test: queue phase removed (add_anim dropped)")


if __name__ == "__main__":
    main()
