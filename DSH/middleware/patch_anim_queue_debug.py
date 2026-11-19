#!/usr/bin/env python3
"""Diagnose the queue phase: is add_anim queuing at all?

Prints the add_anim return value and, every 50 frames, the current entry, its
track time and the queued entry's track time.

Run from the project root:  python DSH/middleware/patch_anim_queue_debug.py
"""
import io

P = "User/spine_anim_test.c"

OLD = """        spine_instance_play(in, anim_a, 0, 0);      /* 不循环 */

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
        }"""

NEW = """        int qok;

        spine_instance_play(in, anim_a, 0, 0);      /* 不循环 */

        qok = spine_instance_add_anim(in, anim_b, 1, 0.0f, 0);

        printf(ANT_TAG "add_anim(%s)=%d  A_time=%.3f\\r\\n",
               anim_b, qok, (double)spine_instance_get_time(in, 0));

        if (qok == 0)
        {
            pass = 0;
        }

        for (int i = 0; i < 400; i++)
        {
            spine_instance_update(in, 1.0f / 60.0f);

            cur = spine_instance_current_anim(in, 0);

            if (((i % 50) == 0) || (i == 399))
            {
                printf(ANT_TAG "  f=%d cur=%s t=%.3f\\r\\n",
                       i, (cur != 0) ? cur : "?", (double)spine_instance_get_time(in, 0));
            }

            if ((cur != 0) && (cur[0] == anim_b[0]))
            {
                switched = 1;
                break;
            }
        }"""


def main():
    s = io.open(P, encoding="utf-8").read()

    if "add_anim(%s)=%d" in s:
        print("already patched")
        return

    assert OLD in s, "queue block not found"
    s = s.replace(OLD, NEW, 1)

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("queue diagnostics added")


if __name__ == "__main__":
    main()
