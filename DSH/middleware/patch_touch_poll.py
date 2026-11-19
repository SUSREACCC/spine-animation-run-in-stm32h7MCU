#!/usr/bin/env python3
"""Touch on this board: poll the GT1151 over I2C instead of using the INT pin.

Why
---
`tp_scan()` gates everything on T_PEN (PH7).  On this board PH7 is a mandatory
SDRAM (FMC) signal: removing it from the SDRAM pin mask makes SDRAM self-test
fail immediately.  So the touch INT line is NOT available while SDRAM is up.

The GT1151 exposes the same information over I2C:
    0x814E  status: bit7 = buffer ready, low nibble = touch points
    0x8150  first point: x_lo x_hi y_lo y_hi
Writing 0 to 0x814E clears the buffer.

This patch adds gt_poll() to the interactive module and uses it instead of
tp_scan(); the raw coordinates are printed so the scaling can be checked.

Run from the project root:  python DSH/middleware/patch_touch_poll.py
"""
import io

P = "User/spine_ik_interactive.c"

POLL = r'''
/*----------------------------------------------------------------- GT1151 轮询
 *
 * 本板 PH7 被 SDRAM 占用（去掉就 SDRAM 自检失败），触摸 INT 不可用。
 * 直接读 GT1151 的状态/坐标寄存器，不依赖 INT 引脚。
 * 返回 1 = 有触摸点（x/y 为 IC 原始坐标）。
 */
#define GT_REG_STATUS   0x814Eu
#define GT_REG_PT0      0x8150u

static int gt_poll(uint16_t *x, uint16_t *y)
{
    uint8_t st = 0;
    uint8_t buf[4] = { 0, 0, 0, 0 };
    uint8_t clr = 0;
    int n;

    gt9xxx_rd_reg(GT_REG_STATUS, &st, 1);

    if ((st & 0x80u) == 0u)
    {
        return 0;                       /* 没有新数据 */
    }

    n = st & 0x0Fu;

    if (n > 0)
    {
        gt9xxx_rd_reg(GT_REG_PT0, buf, 4);
    }

    gt9xxx_wr_reg(GT_REG_STATUS, &clr, 1);   /* 清标志，否则 INT/缓冲一直挂着 */

    if (n == 0)
    {
        return 0;                       /* 抬手 */
    }

    *x = (uint16_t)(((uint16_t)buf[1] << 8) | buf[0]);
    *y = (uint16_t)(((uint16_t)buf[3] << 8) | buf[2]);

    return 1;
}
'''


def main():
    s = io.open(P, encoding="utf-8").read()

    if "gt_poll" in s:
        print("already patched")
        return

    # 1) 插入轮询函数（放在 ik_dist 之后）
    anchor = "int spine_ik_interactive(const char *skel_path"
    s = s.replace(anchor, POLL.strip() + "\n\n" + anchor, 1)

    # 2) 用 gt_poll 替换 tp_scan
    old = """        if ((tp_scan(0) != 0) && ((tp_dev.sta & TP_PRES_DOWN) != 0))
        {
            int mx = (int)tp_dev.x[0];
            int my = (int)tp_dev.y[0];
"""
    new = """        {
            uint16_t rx = 0, ry = 0;

            if (gt_poll(&rx, &ry) != 0)
        {
            int mx = (int)rx;
            int my = (int)ry;
"""
    assert old in s
    s = s.replace(old, new, 1)

    # 补齐多出来的一层大括号
    old_tail = """                if (spine_instance_set_ik_target(in, ik_name, wx, wy) != 0)
                {
                    touched = 1;
                    last_x = mx;
                    last_y = my;

                    printf(IKT_TAG "screen (%d,%d) -> world (%.1f,%.1f)\\r\\n",
                           mx, my, (double)wx, (double)wy);
                }
            }
        }"""
    new_tail = """                if (spine_instance_set_ik_target(in, ik_name, wx, wy) != 0)
                {
                    touched = 1;
                    last_x = mx;
                    last_y = my;

                    printf(IKT_TAG "touch raw(%d,%d) -> world (%.1f,%.1f)\\r\\n",
                           mx, my, (double)wx, (double)wy);
                }
            }
            }
        }"""
    assert old_tail in s
    s = s.replace(old_tail, new_tail, 1)

    # 3) 状态行打印 gt_poll 的原始值
    s = s.replace('(unsigned)HAL_GPIO_ReadPin(GPIOH, GPIO_PIN_7),\n                       (unsigned)tp_dev.x[0], (unsigned)tp_dev.y[0], (unsigned)tp_dev.sta,',
                  '(unsigned)st_last, (unsigned)rx_last, (unsigned)ry_last, (unsigned)sta_last,')

    s = s.replace("    uint32_t t_prev = 0;",
                  "    uint32_t t_prev = 0;\n    uint16_t rx_last = 0, ry_last = 0;\n    uint8_t  st_last = 0;\n    uint16_t sta_last = 0;")

    io.open(P, "w", encoding="utf-8", newline="").write(s)
    print("gt_poll wired into the interactive test")


if __name__ == "__main__":
    main()
