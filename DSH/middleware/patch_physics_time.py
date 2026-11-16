#!/usr/bin/env python3
"""Physics never advanced: PhysicsConstraint::update() derives its delta from
skeleton._time - _lastTime, and _time only moves in Skeleton::update(delta).
No playback path called it, so the delta was always 0 and the constraints never
stepped.  Add skeleton.update(dt) (and per-skeleton in the duo path) before
updateWorldTransform in every frame loop.

Run from the project root:  python DSH/middleware/patch_physics_time.py
"""
import io

PATH = "User/spine_test.cpp"

PLAY_OLD = """        state.update(dt);
        state.apply(skeleton);
        skeleton.updateWorldTransform(spine::Physics_Update);"""
PLAY_NEW = """        state.update(dt);
        state.apply(skeleton);
        skeleton.update(dt);                     /* 推进 _time，物理约束靠它算 delta */
        skeleton.updateWorldTransform(spine::Physics_Update);"""

DUO_OLD = """            skA->updateWorldTransform(spine::Physics_Update);"""
DUO_NEW = """            skA->update(dt);
            skA->updateWorldTransform(spine::Physics_Update);"""

DUO_OLD_B = """            skB->updateWorldTransform(spine::Physics_Update);"""
DUO_NEW_B = """            skB->update(dt);
            skB->updateWorldTransform(spine::Physics_Update);"""

GRAV_OLD = """        if (has_anim)
        {
            state.update(dt);
            state.apply(skeleton);
        }

        skeleton.updateWorldTransform(spine::Physics_Update);"""
GRAV_NEW = """        if (has_anim)
        {
            state.update(dt);
            state.apply(skeleton);
        }

        skeleton.update(dt);                     /* 推进 _time，物理约束靠它算 delta */
        skeleton.updateWorldTransform(spine::Physics_Update);"""


def patch_region(s, start_marker, old, new, label):
    i = s.find(start_marker)
    if i < 0:
        print("  %s: function not found" % label)
        return s
    head, tail = s[:i], s[i:]
    if new.strip() in tail and old not in tail:
        print("  %s: already patched" % label)
        return s
    if old not in tail:
        print("  %s: anchor not found" % label)
        return s
    tail = tail.replace(old, new, 1)
    print("  %s: patched" % label)
    return head + tail


def main():
    s = io.open(PATH, encoding="utf-8").read()

    s = patch_region(s, 'extern "C" uint8_t spine_play(', PLAY_OLD, PLAY_NEW, "spine_play")
    s = patch_region(s, 'extern "C" uint8_t spine_play_duo(', DUO_OLD, DUO_NEW, "duo A")
    s = patch_region(s, 'extern "C" uint8_t spine_play_duo(', DUO_OLD_B, DUO_NEW_B, "duo B")
    s = patch_region(s, 'extern "C" uint8_t spine_gravity_test(', GRAV_OLD, GRAV_NEW, "gravity")

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("done")


if __name__ == "__main__":
    main()
