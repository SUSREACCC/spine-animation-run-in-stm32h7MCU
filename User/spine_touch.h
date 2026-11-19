/**
 ****************************************************************************************************
 * @file        spine_touch.h
 * @brief       GT1158 触摸轮询（不依赖 PH7，纯 I2C）
 *
 * 本板 PH7 被 SDRAM 占用（从 SDRAM 引脚掩码里去掉会直接 SDRAM 自检失败），
 * 所以不能用 T_PEN 中断门控，改成直接读 IC 的寄存器：
 *   0x814E  状态：bit7 = 有新数据，低 4 位 = 触摸点数
 *   0x8150  第一个点：x_lo x_hi y_lo y_hi
 ****************************************************************************************************
 */

#ifndef __SPINE_TOUCH_H
#define __SPINE_TOUCH_H

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 轮询一次。
 * @param x,y 按下时写入 IC 原始坐标
 * @return  1 = 按下，0 = 无新报文（保持原状态），-1 = 抬手
 */
/** 初始化触摸 IC（幂等：多次调用只初始化一次）。返回 1 = 可用 */
int spine_touch_init(void);

int spine_touch_poll(unsigned short *x, unsigned short *y);

/** 最近一次读到的状态字节（调试用） */
unsigned char spine_touch_status(void);

#ifdef __cplusplus
}
#endif

#endif
