/**
 ****************************************************************************************************
 * @file        spine_touch.c
 * @brief       GT1158 触摸轮询实现
 ****************************************************************************************************
 */

#include "spine_touch.h"

#include "./BSP/TOUCH/gt9xxx.h"
#include "./BSP/TOUCH/touch.h"

#define GT_REG_STATUS   0x814Eu
#define GT_REG_PT0      0x8150u

static unsigned char g_gt_st = 0;

int spine_touch_init(void)
{
    static int inited = 0;

    if (inited != 0)
    {
        return 1;
    }

    /* tp_init() 返回 0 = 成功 */
    if (tp_init() != 0)
    {
        return 0;
    }

    inited = 1;

    return 1;
}

unsigned char spine_touch_status(void)
{
    return g_gt_st;
}

int spine_touch_poll(unsigned short *x, unsigned short *y)
{
    unsigned char st = 0;
    unsigned char buf[4] = { 0, 0, 0, 0 };
    unsigned char clr = 0;
    int n;

    gt9xxx_rd_reg(GT_REG_STATUS, &st, 1);
    g_gt_st = st;

    if ((st & 0x80u) == 0u)
    {
        return 0;                       /* 没有新报文 */
    }

    n = st & 0x0Fu;

    if (n > 0)
    {
        gt9xxx_rd_reg(GT_REG_PT0, buf, 4);
    }

    gt9xxx_wr_reg(GT_REG_STATUS, &clr, 1);   /* 清标志，否则缓冲一直挂着 */

    if (n == 0)
    {
        return -1;                      /* 抬手 */
    }

    if (x != 0)
    {
        *x = (unsigned short)(((unsigned short)buf[1] << 8) | buf[0]);
    }

    if (y != 0)
    {
        *y = (unsigned short)(((unsigned short)buf[3] << 8) | buf[2]);
    }

    return 1;
}
