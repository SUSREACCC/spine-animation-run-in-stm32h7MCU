/**
 ****************************************************************************************************
 * @file        sdmmc_sdcard.c
 * @version     V1.0
 * @brief       SD卡 驱动代码
 ****************************************************************************************************
 * @attention   Waiken-Smart 慧勤智远
 *
 * 实验平台:    STM32H743IIT6小系统板
 *
 ****************************************************************************************************
 */

#include "string.h"
#include "./SYSTEM/usart/usart.h"
#include "./BSP/SDMMC/sdmmc_sdcard.h"


SD_HandleTypeDef g_sd_handle;                     /* SD卡句柄 */
HAL_SD_CardInfoTypeDef g_sd_card_info_handle;     /* SD卡信息结构体 */

/* sdmmc_read_disk/sdmmc_write_disk函数专用buf,当这两个函数的数据缓存区地址不是4字节对齐的时候,
 * 需要用到该数组,确保数据缓存区地址是4字节对齐的.
 */
//__ALIGNED(4) uint8_t g_sd_data_buffer[512];


/**
 * @brief       初始化SD卡
 * @param       无
 * @retval      返回值:0,初始化正确;1.初始化错误
 */
uint8_t sd_init(void)
{
    uint8_t SD_Error;
    GPIO_InitTypeDef gpio_init_struct;
  
	  /* 由于SDMMC与摄像头接口共用数据线，需将摄像头接口的PWDN(PI3)引脚拉高，
     * 摄像头POWER DOWN，否则有时候SD卡初始化不通过 
     */
    __HAL_RCC_GPIOI_CLK_ENABLE();                         /* 使能PI口时钟 */

    gpio_init_struct.Pin = GPIO_PIN_3;                    /* PWDN引脚PI3 */
    gpio_init_struct.Mode = GPIO_MODE_OUTPUT_PP;          /* 推挽输出 */
    gpio_init_struct.Pull = GPIO_PULLUP;                  /* 上拉 */
    gpio_init_struct.Speed = GPIO_SPEED_FREQ_MEDIUM;      /* 中速 */
    HAL_GPIO_Init(GPIOI, &gpio_init_struct);              /* 初始化PI3引脚 */
  
    HAL_GPIO_WritePin(GPIOI, GPIO_PIN_3, GPIO_PIN_SET);   /* PI3输出1 */
  
    HAL_SD_DeInit(&g_sd_handle);

    /* 初始化时的时钟不能大于400KHZ */
    g_sd_handle.Instance = SDMMC1;
    g_sd_handle.Init.ClockEdge = SDMMC_CLOCK_EDGE_RISING;                       /* 上升沿 */
    g_sd_handle.Init.ClockPowerSave = SDMMC_CLOCK_POWER_SAVE_DISABLE;           /* 空闲时不关闭时钟电源 */
    /* BOARD FIX (H7spineRuntimeTest):
     * With SDMMC_BUS_WIDE_4B the data phase always times out on this board
     * (HAL_SD_ReadBlocks -> HAL_SD_ERROR_TIMEOUT at 30/15/6 MHz) while CMD-based
     * traffic (CID/CSD, card info) succeeds, i.e. the 4-bit DAT path is not usable.
     * 1-bit transfers run reliably at 30 MHz, so 1-bit is the default here.
     * Set SD_BOARD_BUS4 to 1 to restore the vendor 4-bit behaviour. */
#if SD_BOARD_BUS4
    g_sd_handle.Init.BusWide = SDMMC_BUS_WIDE_4B;
#else
    g_sd_handle.Init.BusWide = SDMMC_BUS_WIDE_1B;
#endif
    g_sd_handle.Init.HardwareFlowControl = SDMMC_HARDWARE_FLOW_CONTROL_DISABLE; /* 关闭硬件流控制 */
    g_sd_handle.Init.ClockDiv = SDMMC_NSpeed_CLK_DIV;                           /* 设置时钟分频系数，配置为默认SD传输时钟频率 
                                                                                 * SDMMC_CK时钟 = sdmmc_ker_ck / [2 * clkdiv]; (sdmmc_ker_ck一般为240Mhz)
                                                                                 */
  
    SD_Error = HAL_SD_Init(&g_sd_handle);
  
    if (SD_Error != HAL_OK)
    {
        return 1;
    }
    
    HAL_SD_GetCardInfo(&g_sd_handle, &g_sd_card_info_handle);                   /* 获取SD卡信息 */

    return 0;
}

/**
 * @brief       SDMMC底层驱动，时钟使能，引脚配置
 * @note        此函数会被HAL_SD_Init()调用
 * @param       hsd:SD卡句柄
 * @retval      无
 */
void HAL_SD_MspInit(SD_HandleTypeDef *hsd)
{
    if (hsd->Instance == SDMMC1)
    {
        GPIO_InitTypeDef gpio_init_struct;

        __HAL_RCC_SDMMC1_CLK_ENABLE();                       /* 使能SDMMC1时钟 */
        SD1_D0_GPIO_CLK_ENABLE();                            /* SD1_D0引脚IO时钟使能 */
        SD1_D1_GPIO_CLK_ENABLE();                            /* SD1_D1引脚IO时钟使能 */
        SD1_D2_GPIO_CLK_ENABLE();                            /* SD1_D2引脚IO时钟使能 */
        SD1_D3_GPIO_CLK_ENABLE();                            /* SD1_D3引脚IO时钟使能 */
        SD1_CLK_GPIO_CLK_ENABLE();                           /* SD1_CLK引脚IO时钟使能 */
        SD1_CMD_GPIO_CLK_ENABLE();                           /* SD1_CMD引脚IO时钟使能 */

        gpio_init_struct.Pin = SD1_D0_GPIO_PIN;              /* SD1_D0引脚 */
        gpio_init_struct.Mode = GPIO_MODE_AF_PP;             /* 复用推挽 */
        gpio_init_struct.Pull = GPIO_PULLUP;                 /* 上拉 */
        gpio_init_struct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;  /* 高速 */
        gpio_init_struct.Alternate = GPIO_AF12_SDIO1;        /* 复用为SDIO */
        HAL_GPIO_Init(SD1_D0_GPIO_PORT, &gpio_init_struct);  /* 初始化SD1_D0引脚 */

        gpio_init_struct.Pin = SD1_D1_GPIO_PIN;              /* SD1_D1引脚 */
        HAL_GPIO_Init(SD1_D1_GPIO_PORT, &gpio_init_struct);  /* 初始化SD1_D1引脚 */

        gpio_init_struct.Pin = SD1_D2_GPIO_PIN;              /* SD1_D2引脚 */
        HAL_GPIO_Init(SD1_D2_GPIO_PORT, &gpio_init_struct);  /* 初始化SD1_D2引脚 */

        gpio_init_struct.Pin = SD1_D3_GPIO_PIN;              /* SD1_D3引脚 */
        HAL_GPIO_Init(SD1_D3_GPIO_PORT, &gpio_init_struct);  /* 初始化SD1_D3引脚 */

        gpio_init_struct.Pin = SD1_CLK_GPIO_PIN;             /* SD1_CLK引脚 */
        HAL_GPIO_Init(SD1_CLK_GPIO_PORT, &gpio_init_struct); /* 初始化SD1_CLK引脚 */

        gpio_init_struct.Pin = SD1_CMD_GPIO_PIN;             /* SD1_CMD引脚 */
        HAL_GPIO_Init(SD1_CMD_GPIO_PORT, &gpio_init_struct); /* 初始化SD1_CMD引脚 */
    }
}

/**
 * @brief       获取卡信息函数
 * @param       cardinfo:SD卡信息句柄
 * @retval      返回值:读取卡信息状态值
 */
uint8_t get_sd_card_info(HAL_SD_CardInfoTypeDef *cardinfo)
{
    uint8_t sta;
    sta = HAL_SD_GetCardInfo(&g_sd_handle, cardinfo);
    return sta;
}

/**
 * @brief       获取SD卡状态
 * @param       无
 * @retval      返回值:SD_TRANSFER_OK      传输完成，可以继续下一次传输
                       SD_TRANSFER_BUSY    SD卡正忙，不可以进行下一次传输
 */
uint8_t get_sd_card_state(void)
{
    return ((HAL_SD_GetCardState(&g_sd_handle) == HAL_SD_CARD_TRANSFER) ? SD_TRANSFER_OK : SD_TRANSFER_BUSY);
}

/**
 * @brief       读SD卡(fatfs/usb调用)
 * @param       pbuf  : 数据缓存区
 * @param       saddr : 扇区地址
 * @param       cnt   : 扇区个数
 * @retval      0, 正常;  其他, 错误(详见SD_Error定义);
 */
uint8_t sd_read_disk(uint8_t *pbuf, uint32_t saddr, uint32_t cnt)
{
    uint8_t  sta;
    uint32_t guard = 2000000u;      /* bounded busy wait (~few ms after HAL returns) */

    /* NOTE: interrupts are intentionally NOT disabled here: the HAL is driven in
     * polling mode and the original sys_intx_disable() + delay_ms() combination
     * would hang (delay_ms needs SysTick). */
    sta = (uint8_t)HAL_SD_ReadBlocks(&g_sd_handle, (uint8_t *)pbuf, saddr, cnt, 1000u);

    while ((get_sd_card_state() != SD_TRANSFER_OK) && (guard != 0u))
    {
        guard--;
    }

    if (guard == 0u)
    {
        return 1u;
    }

    return (sta == HAL_OK) ? 0u : 1u;
}

/**
 * @brief       写SD卡(fatfs/usb调用)
 * @param       pbuf  : 数据缓存区
 * @param       saddr : 扇区地址
 * @param       cnt   : 扇区个数
 * @retval      0, 正常;  其他, 错误(详见SD_Error定义);
 */
uint8_t sd_write_disk(uint8_t *pbuf, uint32_t saddr, uint32_t cnt)
{
    uint8_t  sta;
    uint32_t guard = 2000000u;

    sta = (uint8_t)HAL_SD_WriteBlocks(&g_sd_handle, (uint8_t *)pbuf, saddr, cnt, 1000u);

    while ((get_sd_card_state() != SD_TRANSFER_OK) && (guard != 0u))
    {
        guard--;
    }

    if (guard == 0u)
    {
        return 1u;
    }

    return (sta == HAL_OK) ? 0u : 1u;
}






