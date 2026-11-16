/**
 ****************************************************************************************************
 * @file        main.c
 * @brief       STM32H743 board driver bring-up entry
 * @note        Only clock / console / timebase init here; self-test logic lives in selftest.c
 ****************************************************************************************************
 */

#include "./SYSTEM/sys/sys.h"
#include "./SYSTEM/usart/usart.h"
#include "./SYSTEM/delay/delay.h"
#include "selftest.h"

int main(void)
{
    sys_cache_enable();                                         /* enable L1 cache        */
    HAL_Init();                                                 /* init HAL               */
    sys_stm32_clock_init(192, 5, 2, 4);                         /* SYSCLK = 480 MHz       */
    delay_init(480);                                            /* timebase               */
    usart_init(115200);                                         /* console -> COM11       */

    selftest_run();                                             /* never returns          */

    while (1)
    {
    }
}
