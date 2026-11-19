#!/usr/bin/env python3
"""Make the cached TrackEntry pointers safe.

Problem: AnimationState disposes a TrackEntry when it detaches (e.g. a
non-looping animation completes and a queued one takes over).  We cache
`TrackEntry*` in spine_instance::tracks[] so get_time()/current_anim()/seek()
work, so that disposal left a dangling pointer -> HardFault.

Fix: switch the state to MANUAL track-entry disposal and retire entries one
generation late:
  * play()        : tracks[t] = new entry; retire[t] = previous entry
                    (dispose the entry retired one call earlier)
  * stop()        : clear the track and dispose both cached entries
  * destroy()     : dispose everything, then clear tracks
At most 2 live entries per track, and the disposed one is always 2 switches old,
so its crossfade has long finished.

Run from the project root:  python DSH/middleware/patch_track_entry_lifetime.py
"""
import io

CPP = "User/spine_api.cpp"

OLD_TRACK = "    spine::TrackEntry         *tracks[4];  /* 每条轨道当前的 TrackEntry */"
NEW_TRACK = """    spine::TrackEntry         *tracks[4];  /* 每条轨道当前的 TrackEntry */
    spine::TrackEntry         *retire[4];  /* 上一代条目：混合完成后再回收 */"""

OLD_CREATE = """    in->state = new spine::AnimationState(*in->asd);"""
NEW_CREATE = """    in->state = new spine::AnimationState(*in->asd);

    /* TrackEntry 由我们手动回收：默认模式会在动画播完时自动 dispose，
     * 而我们缓存了指针（get_time/seek 需要），悬空会直接 HardFault。 */
    in->state->setManualTrackEntryDisposal(true);"""

OLD_PLAY = """    in->tracks[track] = &in->state->setAnimation((size_t)track, spine::String(anim), (loop != 0));"""
NEW_PLAY = """    {
        spine::TrackEntry *old = in->tracks[track];
        spine::TrackEntry *ne = &in->state->setAnimation((size_t)track, spine::String(anim), (loop != 0));

        /* 上一代（更早的那次切换遗留）此时混合早已结束，可以安全回收 */
        if ((in->retire[track] != nullptr) &&
            (in->retire[track] != old) &&
            (in->retire[track] != ne))
        {
            in->state->disposeTrackEntry(in->retire[track]);
        }

        in->retire[track] = old;
        in->tracks[track] = ne;
    }"""

OLD_STOP = """    if ((in != nullptr) && (track >= 0) && (track < 4))
    {
        in->state->clearTrack((size_t)track);
        in->tracks[track] = nullptr;
    }"""
NEW_STOP = """    if ((in != nullptr) && (track >= 0) && (track < 4))
    {
        in->state->clearTrack((size_t)track);

        if (in->tracks[track] != nullptr)
        {
            in->state->disposeTrackEntry(in->tracks[track]);
        }

        if (in->retire[track] != nullptr)
        {
            in->state->disposeTrackEntry(in->retire[track]);
        }

        in->tracks[track] = nullptr;
        in->retire[track] = nullptr;
    }"""

OLD_DESTROY = """    delete in->renderer;
    delete in->state;"""
NEW_DESTROY = """    for (int i = 0; i < 4; i++)
    {
        if (in->tracks[i] != nullptr)
        {
            in->state->disposeTrackEntry(in->tracks[i]);
            in->tracks[i] = nullptr;
        }

        if (in->retire[i] != nullptr)
        {
            in->state->disposeTrackEntry(in->retire[i]);
            in->retire[i] = nullptr;
        }
    }

    delete in->renderer;
    delete in->state;"""


def main():
    s = io.open(CPP, encoding="utf-8").read()

    if "retire[4]" in s:
        print("already patched")
        return

    for old, new, what in (
        (OLD_TRACK, NEW_TRACK, "struct"),
        (OLD_CREATE, NEW_CREATE, "create"),
        (OLD_PLAY, NEW_PLAY, "play"),
        (OLD_STOP, NEW_STOP, "stop"),
        (OLD_DESTROY, NEW_DESTROY, "destroy"),
    ):
        assert old in s, what + " pattern not found"
        s = s.replace(old, new, 1)
        print("patched:", what)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)


if __name__ == "__main__":
    main()
