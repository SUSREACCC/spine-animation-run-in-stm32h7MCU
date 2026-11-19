#!/usr/bin/env python3
"""Fix the queue-next-animation phase of spine_anim_test.

The first draft froze the track then seeked past the end, which never lets a
queued animation start (a looping TrackEntry never completes).  Use a
non-looping entry and step until the queued animation takes over.

Run from the project root:  python DSH/middleware/patch_anim_test_queue.py
"""
import io

P = "User/spine_anim_test.c"

OLD = """    /* ---- 5. 排队下一段 ---- */
    {
        spine_instance_play(in, anim_a, 1, 0);

        if (spine_instance_add_anim(in, anim_b, 1, 0.0f, 0) == 0)
        {
            pass = 0;
        }

        spine_instance_set_time(in, 0.0f, 0);        /* 定格，确保这一段很短就播完？不：改成直接推进 */

        /* 用 seek 把 A 推到接近结尾，让排队动画尽快接管 */
        spine_instance_seek(in, 100.0f, 0);
        spine_instance_set_speed(in, 1.0f, 0);

        ant_step(in, 8);

        cur = spine_instance_current_anim(in, 0);
        printf(ANT_TAG "queued -> now %s (期望 %s)\\r\\n", (cur != 0) ? cur : "?", anim_b);

        if ((cur == 0) || (cur[0] != anim_b[0]))
        {
            pass = 0;
        }
    }"""

NEW = """    /* ---- 5. 排队下一段：A 不循环，播完后 B 自动接管 ---- */
    {
        int switched = 0;

        spine_instance_play(in, anim_a, 0, 0);      /* 不循环 */

        if (spine_instance_add_anim(in, anim_b, 1, 0.0f, 0) == 0)
        {
            pass = 0;
        }

        for (int i = 0; i < 400; i++)
        {
            spine_instance_update(in, 1.0f / 60.0f);

            cur = spine_instance_current_anim(in, 0);

            if ((cur != 0) && (cur[0] == anim_b[0]))
            {
                switched = 1;
                break;
            }
        }

        printf(ANT_TAG "queued -> now %s (期望 %s, 切换=%d)\\r\\n",
               (cur != 0) ? cur : "?", anim_b, switched);

        if (switched == 0)
        {
            pass = 0;
        }
    }"""


def main():
    s = io.open(P, encoding="utf-8").read()

    if "int switched = 0" in s:
        print("already patched")
        return

    assert OLD in s, "queue block not found"
    s = s.replace(OLD, NEW, 1)

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("anim test: queue phase rewritten")


if __name__ == "__main__":
    main()
