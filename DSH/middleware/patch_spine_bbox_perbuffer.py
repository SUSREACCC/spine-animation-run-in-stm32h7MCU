#!/usr/bin/env python3
"""Track the dirty rect per framebuffer (double buffering has a 2-frame lag).

Each buffer holds the frame rendered two frames ago, so clearing only the union
of the current and previous frame leaves the older frame's extremities behind.

Run from the project root:  python DSH/middleware/patch_spine_bbox_perbuffer.py
"""
import io

PATH = "User/spine_test.cpp"


def main():
    s = io.open(PATH, encoding="utf-8").read()

    if "pbx[2]" in s:
        print("already patched")
        return

    old = """    /* 上一帧的包围盒（第一帧为空），每帧与当前帧取并集做局部清屏 */
    int pbx0 = 0, pby0 = 0, pbx1 = -1, pby1 = -1;"""
    new = """    /* 每块缓冲各自的上一帧包围盒：双缓冲有 2 帧延迟，
     * 只清"当前+上一帧"会漏掉两帧前的残影（实测 740 px 落在框外）。 */
    int pbx[2] = { 0, 0 };
    int pby[2] = { 0, 0 };
    int pbX[2] = { -1, -1 };
    int pbY[2] = { -1, -1 };
    int parity = 0;"""
    if old not in s:
        raise SystemExit("prev-bbox block not found")
    s = s.replace(old, new, 1)

    old2 = """        int dbx0 = (pbx1 < 0) ? cbx0 : ((cbx0 < pbx0) ? cbx0 : pbx0);
        int dby0 = (pby1 < 0) ? cby0 : ((cby0 < pby0) ? cby0 : pby0);
        int dbx1 = (pbx1 < 0) ? cbx1 : ((cbx1 > pbx1) ? cbx1 : pbx1);
        int dby1 = (pby1 < 0) ? cby1 : ((cby1 > pby1) ? cby1 : pby1);"""
    new2 = """        int dbx0 = (pbX[parity] < 0) ? cbx0 : ((cbx0 < pbx[parity]) ? cbx0 : pbx[parity]);
        int dby0 = (pbX[parity] < 0) ? cby0 : ((cby0 < pby[parity]) ? cby0 : pby[parity]);
        int dbx1 = (pbX[parity] < 0) ? cbx1 : ((cbx1 > pbX[parity]) ? cbx1 : pbX[parity]);
        int dby1 = (pbX[parity] < 0) ? cby1 : ((cby1 > pbY[parity]) ? cby1 : pbY[parity]);"""
    if old2 not in s:
        raise SystemExit("union block not found")
    s = s.replace(old2, new2, 1)

    old3 = "        pbx0 = cbx0; pby0 = cby0; pbx1 = cbx1; pby1 = cby1;"
    new3 = """        pbx[parity] = cbx0;
        pby[parity] = cby0;
        pbX[parity] = cbx1;
        pbY[parity] = cby1;

        parity ^= 1;"""
    if old3 not in s:
        raise SystemExit("save block not found")
    s = s.replace(old3, new3, 1)

    io.open(PATH, "w", encoding="utf-8", newline="").write(s)
    print("per-buffer dirty rect installed")


if __name__ == "__main__":
    main()
