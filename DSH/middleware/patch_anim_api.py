#!/usr/bin/env python3
"""Add the animation-transition API to spine_api.

Declarations go into User/spine_api.h, implementation into User/spine_api.cpp
(where struct spine_instance lives, so no duplicated layout).

    void        spine_instance_set_default_mix(spine_instance_t *in, float seconds);
    int         spine_instance_set_mix(spine_instance_t *in, const char *from,
                                       const char *to, float seconds);
    int         spine_instance_add_anim(spine_instance_t *in, const char *anim,
                                        int loop, float delay, int track);
    float       spine_instance_get_time(spine_instance_t *in, int track);
    const char *spine_instance_current_anim(spine_instance_t *in, int track);
    int         spine_instance_seek(spine_instance_t *in, float seconds, int track);

Notes
  * AnimationStateData::setMix(name, name, d) asserts when a name is unknown, so
    we resolve both animations first and call the Animation& overload.
  * spine_instance_set_time() zeroes timeScale (freeze).  spine_instance_seek()
    keeps it, which is what "resume the walking progress" needs.

Run from the project root:  python DSH/middleware/patch_anim_api.py
"""
import io

H = "User/spine_api.h"
CPP = "User/spine_api.cpp"

H_ADD = r'''
/*==================================================================================================
 * 动画衔接（过渡时长 / 排队 / 进度接回）
 *
 * 默认 defaultMix = 0，即 play() 切换动画是硬切；先 set_default_mix() 才有过渡。
 *=================================================================================================*/

/** 设置默认过渡时长（秒）。0 = 硬切 */
void spine_instance_set_default_mix(spine_instance_t *in, float seconds);

/** 设置 from -> to 的过渡时长（秒）。两个动画都要存在，否则返回 0 */
int spine_instance_set_mix(spine_instance_t *in, const char *from, const char *to, float seconds);

/** 排队下一段动画（当前段结束后按 delay 秒开始）。返回 1 = 成功 */
int spine_instance_add_anim(spine_instance_t *in, const char *anim, int loop, float delay, int track);

/** 读取当前播放进度（秒）*/
float spine_instance_get_time(spine_instance_t *in, int track);

/** 读取当前动画名；该轨没有动画时返回 NULL */
const char *spine_instance_current_anim(spine_instance_t *in, int track);

/** 跳到指定进度并保留时间缩放（切换动画后接回原进度用）。返回 1 = 成功 */
int spine_instance_seek(spine_instance_t *in, float seconds, int track);
'''

CPP_ADD = r'''
/*----------------------------------------------------------------- 动画衔接 */

void spine_instance_set_default_mix(spine_instance_t *in, float seconds)
{
    if ((in == nullptr) || (in->asd == nullptr))
    {
        return;
    }

    if (seconds < 0.0f)
    {
        seconds = 0.0f;
    }

    in->asd->setDefaultMix(seconds);
}

int spine_instance_set_mix(spine_instance_t *in, const char *from, const char *to, float seconds)
{
    if ((in == nullptr) || (in->asd == nullptr) || (in->asset == nullptr) ||
        (from == nullptr) || (to == nullptr))
    {
        return 0;
    }

    /* 先查存在性：setMix(String,String,..) 内部是 assert，名字写错会直接断言 */
    spine::Animation *fa = in->asset->data->findAnimation(spine::String(from));
    spine::Animation *ta = in->asset->data->findAnimation(spine::String(to));

    if ((fa == nullptr) || (ta == nullptr))
    {
        return 0;
    }

    if (seconds < 0.0f)
    {
        seconds = 0.0f;
    }

    in->asd->setMix(*fa, *ta, seconds);

    return 1;
}

int spine_instance_add_anim(spine_instance_t *in, const char *anim, int loop, float delay, int track)
{
    if ((in == nullptr) || (in->state == nullptr) || (in->asset == nullptr) ||
        (anim == nullptr) || (track < 0) || (track >= 4))
    {
        return 0;
    }

    spine::Animation *a = in->asset->data->findAnimation(spine::String(anim));

    if (a == nullptr)
    {
        return 0;
    }

    if (delay < 0.0f)
    {
        delay = 0.0f;
    }

    in->state->addAnimation((size_t)track, *a, (loop != 0), delay);

    return 1;
}

float spine_instance_get_time(spine_instance_t *in, int track)
{
    if ((in == nullptr) || (track < 0) || (track >= 4) || (in->tracks[track] == nullptr))
    {
        return 0.0f;
    }

    return in->tracks[track]->getTrackTime();
}

const char *spine_instance_current_anim(spine_instance_t *in, int track)
{
    if ((in == nullptr) || (track < 0) || (track >= 4) || (in->tracks[track] == nullptr))
    {
        return nullptr;
    }

    return in->tracks[track]->getAnimation().getName().buffer();
}

int spine_instance_seek(spine_instance_t *in, float seconds, int track)
{
    if ((in == nullptr) || (track < 0) || (track >= 4) || (in->tracks[track] == nullptr))
    {
        return 0;
    }

    spine::TrackEntry *te = in->tracks[track];

    if (seconds < 0.0f)
    {
        seconds = 0.0f;
    }

    /* 保留 timeScale：set_time() 会清零做成"定格"，接回进度时不能这样 */
    float ts = te->getTimeScale();

    te->setTrackTime(seconds);
    te->setTimeScale(ts);

    return 1;
}
'''


def main():
    h = io.open(H, encoding="utf-8").read()

    if "spine_instance_set_default_mix" in h:
        print("header: already patched")
    else:
        anchor = "/** 已注册实例数（诊断用；实例创建时自动注册，销毁时自动注销） */"
        assert anchor in h, "header anchor not found"
        h = h.replace(anchor, H_ADD.strip() + "\n\n" + anchor, 1)
        io.open(H, "w", encoding="utf-8", newline="").write(h)
        print("header: animation transition API added")

    s = io.open(CPP, encoding="utf-8").read()

    if "spine_instance_set_default_mix" in s:
        print("cpp: already patched")
        return

    anchor = "/*----------------------------------------------------------------- 变换与外观 */"
    assert anchor in s, "cpp anchor not found"
    s = s.replace(anchor, CPP_ADD.strip() + "\n\n" + anchor, 1)

    # 需要的头
    if "#include <spine/Animation.h>" not in s:
        s = s.replace("#include <spine/Skeleton.h>",
                      "#include <spine/Skeleton.h>\n#include <spine/Animation.h>", 1)

    io.open(CPP, "w", encoding="utf-8", newline="").write(s)
    print("cpp: animation transition API implemented")


if __name__ == "__main__":
    main()
