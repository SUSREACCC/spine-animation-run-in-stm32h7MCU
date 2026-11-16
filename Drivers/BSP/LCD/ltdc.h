/**
 ****************************************************************************************************
 * @file        ltdc.h
 * @version     V1.0
 * @brief       LTDC ????????
 ****************************************************************************************************
 * @attention   Waiken-Smart ???????
 *
 * ?????:    STM32H743IIT6С????
 *
 ****************************************************************************************************
 */

#ifndef _LTDC_H
#define _LTDC_H

#include "./SYSTEM/sys/sys.h"


/* ?????????8??800X1280RGB??
 * 0: ??????8??RGB??
 * 1: ???8??RGB??
 */
#define RGB_80_8001280       0     /* ???????8??800X1280RGB?? */


/* LCD LTDC????????? */
typedef struct  
{
    uint32_t pwidth;       /* LTDC???????,???????,?????????????,????0,???????κ?RGB?????? */
    uint32_t pheight;      /* LTDC??????,???????,????????????? */
    uint16_t hsw;          /* ????????? */
    uint16_t vsw;          /* ?????????? */
    uint16_t hbp;          /* ?????? */
    uint16_t vbp;          /* ??????? */
    uint16_t hfp;          /* ????? */
    uint16_t vfp;          /* ??????  */
    uint8_t activelayer;   /* ???????:0/1 */
    uint8_t dir;           /* 0,????;1,????; */
    uint16_t width;        /* LTDC???? */
    uint16_t height;       /* LTDC??? */
    uint32_t pixsize;      /* ??????????????? */
    uint8_t pixformat;     /* ????????? */
}_ltdc_dev; 

extern _ltdc_dev lcdltdc;                     /* ????LCD LTDC???? */
extern LTDC_HandleTypeDef g_ltdc_handle;      /* LTDC??? */
extern DMA2D_HandleTypeDef g_dma2d_handle;    /* DMA2D??? */


#define LTDC_PIXFORMAT_ARGB8888      0X00     /* ARGB8888??? */
#define LTDC_PIXFORMAT_RGB888        0X01     /* RGB888??? */
#define LTDC_PIXFORMAT_RGB565        0X02     /* RGB565??? */
#define LTDC_PIXFORMAT_ARGB1555      0X03     /* ARGB1555??? */
#define LTDC_PIXFORMAT_ARGB4444      0X04     /* ARGB4444??? */
#define LTDC_PIXFORMAT_L8            0X05     /* L8??? */
#define LTDC_PIXFORMAT_AL44          0X06     /* AL44??? */
#define LTDC_PIXFORMAT_AL88          0X07     /* AL88??? */

/******************************************************************************************/
/* LTDC_DE/VSYNC/HSYNC/CLK/BL/RST ???? ???? 
 * LTDC_R0~R7, G0~G7, B0~B7,???????????,?????????????,?????ltcd_init???????.??????????????,
 * ???????6??IO??, ?????ltcd_init?????R0~R7, G0~G7, B0~B7?????IO??.
 */

#define LTDC_DE_GPIO_PORT               GPIOF
#define LTDC_DE_GPIO_PIN                GPIO_PIN_10
#define LTDC_DE_GPIO_CLK_ENABLE()       do{ __HAL_RCC_GPIOF_CLK_ENABLE(); }while(0)    /* ????IO???????? */

#define LTDC_VSYNC_GPIO_PORT            GPIOI
#define LTDC_VSYNC_GPIO_PIN             GPIO_PIN_9
#define LTDC_VSYNC_GPIO_CLK_ENABLE()    do{ __HAL_RCC_GPIOI_CLK_ENABLE(); }while(0)    /* ????IO???????? */

#define LTDC_HSYNC_GPIO_PORT            GPIOI
#define LTDC_HSYNC_GPIO_PIN             GPIO_PIN_10
#define LTDC_HSYNC_GPIO_CLK_ENABLE()    do{ __HAL_RCC_GPIOI_CLK_ENABLE(); }while(0)    /* ????IO???????? */

#define LTDC_CLK_GPIO_PORT              GPIOG
#define LTDC_CLK_GPIO_PIN               GPIO_PIN_7
#define LTDC_CLK_GPIO_CLK_ENABLE()      do{ __HAL_RCC_GPIOG_CLK_ENABLE(); }while(0)    /* ????IO???????? */

#define LTDC_BL_GPIO_PORT               GPIOD
#define LTDC_BL_GPIO_PIN                GPIO_PIN_12
#define LTDC_BL_GPIO_CLK_ENABLE()       do{ __HAL_RCC_GPIOD_CLK_ENABLE(); }while(0)    /* ????IO???????? */

#define LTDC_RST_GPIO_PORT              GPIOD
#define LTDC_RST_GPIO_PIN               GPIO_PIN_11
#define LTDC_RST_GPIO_CLK_ENABLE()      do{ __HAL_RCC_GPIOD_CLK_ENABLE(); }while(0)    /* ????IO???????? */


/* ?????????????,?????RGB565 */
#define LTDC_PIXFORMAT           LTDC_PIXFORMAT_RGB565

/* ??????????????? */
#define LTDC_BACKLAYERCOLOR      0X00000000

/* LTDC???????????,????????SDRAM????. */
#define LTDC_FRAME_BUF_ADDR      0XC0000000  

/* LTDC??????? */
#define LTDC_BL(x)      do{ x ? \
                            HAL_GPIO_WritePin(LTDC_BL_GPIO_PORT, LTDC_BL_GPIO_PIN, GPIO_PIN_SET) : \
                            HAL_GPIO_WritePin(LTDC_BL_GPIO_PORT, LTDC_BL_GPIO_PIN, GPIO_PIN_RESET); \
                        }while(0)

/* LTDC??λ???? */
#define LTDC_RST(x)     do{ x ? \
                            HAL_GPIO_WritePin(LTDC_RST_GPIO_PORT, LTDC_RST_GPIO_PIN, GPIO_PIN_SET) : \
                            HAL_GPIO_WritePin(LTDC_RST_GPIO_PORT, LTDC_RST_GPIO_PIN, GPIO_PIN_RESET); \
                        }while(0)

/******************************************************************************************/

void ltdc_switch(uint8_t sw);                                                                                   /* LTDC???? */
void ltdc_layer_switch(uint8_t layerx, uint8_t sw);                                                             /* ???? */
void ltdc_select_layer(uint8_t layerx);                                                                         /* ????? */
void ltdc_display_dir(uint8_t dir);                                                                             /* LTDC??????????? */
void ltdc_draw_point(uint16_t x, uint16_t y, uint32_t color);                                                   /* LTDC?????? */
uint32_t ltdc_read_point(uint16_t x, uint16_t y);                                                               /* LTDC?????? */
void ltdc_fill(uint16_t sx, uint16_t sy, uint16_t ex, uint16_t ey, uint32_t color);                             /* ???ε?????, DMA2D??? */
void ltdc_color_fill(uint16_t sx, uint16_t sy, uint16_t ex, uint16_t ey, uint16_t *color);                      /* ???β?????, DMA2D??? */
void ltdc_clear(uint32_t color);                                                                                /* LTDC???????? */
uint8_t ltdc_clk_set(uint32_t pll3n, uint32_t pll3m, uint32_t pll3r);                                           /* LTDC??????? */
void ltdc_layer_window_config(uint8_t layerx, uint16_t sx, uint16_t sy, uint16_t width, uint16_t height);       /* LTDC???????? */
void ltdc_layer_parameter_config(uint8_t layerx, uint32_t bufaddr, uint8_t pixformat, uint8_t alpha, uint8_t alpha0, uint8_t bfac1, uint8_t bfac2, uint32_t bkcolor); /* LTDC????????????? */
uint16_t ltdc_panelid_read(void);                                                                               /* LTDC ???ID??????? */
void ltdc_init(void);                                                                                           /* LTDC????????? */

#endif 

                        
                        
                    

