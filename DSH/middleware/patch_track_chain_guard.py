#!/usr/bin/env python3
"""Only dispose a retired TrackEntry when it is no longer in any mixing chain.

First attempt disposed the entry retired one call earlier, but rapid switches
leave the previous entry still attached as `mixingFrom` of the current one ->
disposing it corrupted the state and HardFaulted on the next update.

Rule: dispose a retired entry only if it cannot be reached by walking
`getMixingFrom()` from the current entry (and it is not the current entry).

Run from the project root:  python DSH/middleware/patch_track_chain_guard.py
"""
import io

CPP = "User/spine_api.cpp"

OLD = """        /* 上一代（更早的那次切换遗留）此时混合早已结束，可以安全回收 */
        if ((in->retire[track] != nullptr) &&
            (in->retire[track] != old) &&
            (in->retire[track] != ne))
        {
            in->state->disposeTrackEntry(in->retire[track]);
        }"""

NEW = """        /* 只有确认它已经不在任何混合链里，才能回收 */
        if ((in->retire[track] != nullptr) &&
            (in->retire[track] != old) &&
            (in->retire[track] != ne))
        {
            int in_chain = 0;
            spine::TrackEntry *m = ne->getMixingFrom();

            while (m != nullptr)
            {
                if (m == in->retire[track])
                {
                    in_chain = 1;
                    break;
                }

                m = m->getMixingFrom();
            }

            if (in_chain == 0)
            {
                in->state->disposeTrackEntry(in->retire[track]);
            }
        }"""


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "in_chain" in s:
        print("already patched")
        return

    assert OLD in s, "dispose block not found"
    s = s.replace(OLD, NEW, 1)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("play(): retired entry is now guarded by the mixing chain")


if __name__ == "__main__":
    main()
