#!/usr/bin/env python3
"""current_anim()/get_time()/seek() must follow queued takeovers.

We cache the TrackEntry created by play(); add_anim() queues another entry on
that track, and when the first one ends the queued entry becomes the live one.
Reading the cached entry then reports the OLD animation.

Fix: walk the `next` chain (TrackEntry::getNext is public) and pick the last
entry that has actually started (trackTime > 0).

Run from the project root:  python DSH/middleware/patch_track_current.py
"""
import io

CPP = "User/spine_api.cpp"

HELPER = """/* 返回该轨道上真正在播的条目：排队的动画接管后，沿 next 链跳过旧的 */
static spine::TrackEntry *cur_entry(spine_instance_t *in, int track)
{
    if ((in == nullptr) || (track < 0) || (track >= 4))
    {
        return nullptr;
    }

    spine::TrackEntry *te = in->tracks[track];

    while ((te != nullptr) && (te->getNext() != nullptr))
    {
        if (te->getNext()->getTrackTime() > 0.0f)
        {
            te = te->getNext();     /* 下一段已开始 */
        }
        else
        {
            break;                  /* 还在排队的下一段 */
        }
    }

    return te;
}

"""

OLD_TIME = """    if ((in == nullptr) || (track < 0) || (track >= 4) || (in->tracks[track] == nullptr))
    {
        return 0.0f;
    }

    return in->tracks[track]->getTrackTime();"""
NEW_TIME = """    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return 0.0f;
    }

    return te->getTrackTime();"""

OLD_NAME = """    if ((in == nullptr) || (track < 0) || (track >= 4) || (in->tracks[track] == nullptr))
    {
        return nullptr;
    }

    return in->tracks[track]->getAnimation().getName().buffer();"""
NEW_NAME = """    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return nullptr;
    }

    return te->getAnimation().getName().buffer();"""

OLD_SEEK = """    if ((in == nullptr) || (track < 0) || (track >= 4) || (in->tracks[track] == nullptr))
    {
        return 0;
    }

    spine::TrackEntry *te = in->tracks[track];"""
NEW_SEEK = """    spine::TrackEntry *te = cur_entry(in, track);

    if (te == nullptr)
    {
        return 0;
    }"""


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "cur_entry" in s:
        print("already patched")
        return

    anchor = "float spine_instance_get_time(spine_instance_t *in, int track)"
    assert anchor in s, "get_time not found"
    s = s.replace(anchor, HELPER + anchor, 1)

    for old, new, what in ((OLD_TIME, NEW_TIME, "get_time"),
                           (OLD_NAME, NEW_NAME, "current_anim"),
                           (OLD_SEEK, NEW_SEEK, "seek")):
        assert old in s, what + " body not found"
        s = s.replace(old, new, 1)
        print("patched:", what)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)


if __name__ == "__main__":
    main()
