/**
 ****************************************************************************************************
 * @file        selftest.h
 * @brief       Board-level driver self-test (SDRAM / LCD / QSPI Flash / SD card)
 * @note        Console: USART1 (PA9/PA10) @115200 -> CH340 -> COM11
 ****************************************************************************************************
 */

#ifndef __SELFTEST_H
#define __SELFTEST_H

#include "./SYSTEM/sys/sys.h"

/* self-test result codes (returned by each test_xxx) */
#define ST_OK       0
#define ST_FAIL     1
#define ST_SKIP     2

/**
 * @brief  Run every self-test, then enter heartbeat loop (never returns)
 */
void selftest_run(void);

#endif
