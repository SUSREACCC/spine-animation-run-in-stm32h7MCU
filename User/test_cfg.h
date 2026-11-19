/**
 ****************************************************************************************************
 * @file        test_cfg.h
 * @brief       测试开关：按需启用，默认只跑当前关心的项目
 *
 * 置 1 的测试才会被编译进 selftest_run()。关掉的测试连调用都不会生成，
 * 上电后直接跳到下一个启用的项目，省时间也省 Flash。
 ****************************************************************************************************
 */

#ifndef __TEST_CFG_H
#define __TEST_CFG_H

/*--------------------------------------------------------------------------- 硬件自检 */

/** SDRAM / LCD / QSPI / SD / FATFS 驱动自检（约 5 s）
 *  必须为 1：test_lcd() 里执行 lcd_init()，关掉就没有显示初始化了 */
#ifndef TEST_DRIVERS
#define TEST_DRIVERS        1
#endif

/*--------------------------------------------------------------------------- 渲染器 */

/** raster2d 回归测试（图元 / 混合模式 / 裁剪） */
#ifndef TEST_RASTER
#define TEST_RASTER         0
#endif

/** 帧缓冲基准（写带宽 / 缓存模式对比） */
#ifndef TEST_FBBENCH
#define TEST_FBBENCH        0
#endif

/*--------------------------------------------------------------------------- Spine 旧项目 */

/** 素材总览（动画列表 + 全图渲染） */
#ifndef TEST_SHEET
#define TEST_SHEET          0
#endif

/** 物理重力方向测试（celestial 素材） */
#ifndef TEST_GRAVITY
#define TEST_GRAVITY        0
#endif

/** 双角色压力测试（全分辨率 + 半分辨率各 2 轮） */
#ifndef TEST_DUO
#define TEST_DUO            0
#endif

/** spine_api 最小示例（20 秒左右） */
#ifndef TEST_API_DEMO
#define TEST_API_DEMO       0
#endif

/*--------------------------------------------------------------------------- Spine 当前项目 */

/** IK 目标驱动测试（spineboy 素材，含 7 个 IK 约束） */
#ifndef TEST_IK
#define TEST_IK             1
#endif

/** 6 场景循环展示（不返回；会一直跑下去） */
#ifndef TEST_DEMO
#define TEST_DEMO           0
#endif

/** 触摸屏（GT9xxx / FT5206 软 IIC，PB12/PB13） */
#ifndef TEST_TOUCH
#define TEST_TOUCH           1
#endif

/** 交互测试：点击屏幕驱动 IK 目标（需要 TEST_TOUCH） */
#ifndef TEST_IK_INTERACTIVE
#define TEST_IK_INTERACTIVE  1
#endif

/** 交互测试运行秒数；0 = 永久（默认，方便随时触摸） */
#ifndef TEST_IK_TOUCH_SECONDS
#define TEST_IK_TOUCH_SECONDS 0
#endif

/*--------------------------------------------------------------------------- 兜底 */

/** 关掉 demo 时，自检结束后进入心跳循环 */
#ifndef TEST_HEARTBEAT
#define TEST_HEARTBEAT      1
#endif

/** 松开触摸后回到动画的混合帧数；0 = 立即恢复 */
#ifndef TEST_IK_RELEASE_BLEND
#define TEST_IK_RELEASE_BLEND 8
#endif

/** 动画衔接测试（过渡 / 排队 / 进度接回） */
#ifndef TEST_ANIM_MIX
#define TEST_ANIM_MIX        1
#endif

/** 动画序列：walk 5s -> idle 5s -> aim 10s(触摸驱动 aim-ik) -> death 5s(单次) */
#ifndef TEST_ANIM_SEQ
#define TEST_ANIM_SEQ        1
#endif

#endif /* __TEST_CFG_H */
