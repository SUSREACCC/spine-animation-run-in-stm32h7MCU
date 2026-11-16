# 板级驱动移植说明（SDRAM / LCD / QSPI NOR / SD 卡）

> 平台：慧勤智远 STM32H743IIT6 V1.3 + 4.3" IPS 800×480 RGB 屏
> 工具链：MDK 5.24 / ARM Compiler 5（AC5），纯 C
> 位置：`Drivers/BSP/`（移植自开发板例程）、`User/selftest.c`（自检）、`DSH/middleware/`（构建/烧写/串口脚本）
> 最近更新：2026-11-14 17:2x — SD 触点清洁后 **4-bit @30 MHz 全速通过（11.8 MB/s）**

---

## 1. 目录与来源

| 本项目路径 | 来源例程 | 说明 |
|---|---|---|
| `Drivers/BSP/MPU/{mpu.c,h}` | 实验11 | MPU 区域配置（SDRAM 可缓存/可缓冲；**必须**在 `sdram_init()` 前调用） |
| `Drivers/BSP/SDRAM/{sdram.c,h}` | 实验11 | FMC Bank5，32 MB @ `0xC0000000`，110 MHz |
| `Drivers/BSP/LCD/{lcd.c,h}`、`ltdc.c/h`、`lcdfont.h`、`tft_spi.c/h` | 实验12 | LTDC + DMA2D，RGB565，帧缓冲在 SDRAM |
| `Drivers/BSP/QSPI/{qspi.c,h}` | 实验22 | QUADSPI 底层 |
| `Drivers/BSP/NORFLASH/{norflash.c,h}` | 实验22 | W25Q128（16 MB）读写/擦除 |
| `Drivers/BSP/SDMMC/{sdmmc_sdcard.c,h}` | 实验27 | SDMMC1，**4-bit SDIO @30 MHz**（见 §5.1） |
| `Drivers/BSP/LED/{led.c,h}` | 实验11 | 心跳指示 |
| `Middlewares/FATFS/source/` | 实验28 | FatFs R0.14b + 自研 `diskio.c`/`ffsystem.c`（见 §3.5） |
| `User/selftest.c/.h` | 自研 | 4 项驱动的上电自检 + 屏幕汇总 |

HAL 模块（`Drivers/STM32H7xx_HAL_Driver`）本就齐全（123 个），只需在工程里**加入编译**：
`hal_ltdc(_ex)`、`hal_dma2d`、`hal_sdram`、`hal_sram`、`hal_qspi`、`hal_mdma`、`hal_sd(_ex)`、`hal_dma_ex`、`hal_tim(_ex)`，以及 LL 层 `ll_fmc`、`ll_sdmmc`。
`User/stm32h7xx_hal_conf.h` 中这些模块已默认使能，**无需修改**。

---

## 2. 初始化顺序（关键）

```c
sys_cache_enable();                 /* L1 I/D Cache          */
HAL_Init();
sys_stm32_clock_init(192,5,2,4);    /* 480 MHz               */
delay_init(480);
usart_init(115200);                 /* 控制台 USART1 PA9/PA10 */
led_init();

mpu_memory_protection();            /* 必须先于 SDRAM！        */
sdram_init();                       /* 32 MB @ 0xC0000000     */
lcd_init();                         /* LTDC + DMA2D + 帧缓冲   */
norflash_init();                    /* QSPI NOR               */
sd_init();                          /* SDMMC1                 */
```

顺序原因：SDRAM 的 MPU 属性决定后续 Cache 行为；LTDC 的帧缓冲声明在 `0xC0000000`（`ltdc.c` 中的 `ltdc_lcd_framebuf[1280][800]`），必须在 SDRAM 初始化后使能 LTDC。

---

## 3. 各驱动接口速查

### 3.1 SDRAM（`sdram.h`）
```c
void sdram_init(void);
void sdram_initialization_sequence(void);
uint8_t sdram_send_cmd(uint8_t bankx, uint8_t cmd, uint8_t refresh, uint16_t regval);
void fmc_sdram_read_buffer(uint8_t *pbuf, uint32_t readaddr, uint32_t n);
void fmc_sdram_write_buffer(uint8_t *pbuf, uint32_t writeaddr, uint32_t n);
/* 直接访问：基址 0xC0000000，容量 32 MB */
```

### 3.2 LCD / LTDC（`lcd.h` + `ltdc.h`）
```c
void lcd_init(void);
void lcd_clear(uint32_t color);
void lcd_fill(uint16_t sx, uint16_t sy, uint16_t ex, uint16_t ey, uint32_t color);
void lcd_draw_point(uint16_t x, uint16_t y, uint32_t color);
uint32_t lcd_read_point(uint16_t x, uint16_t y);
void lcd_show_string(uint16_t x, uint16_t y, uint16_t w, uint16_t h,
                     uint8_t size, char *str, uint32_t color);   /* size: 12/16/24/32 */
extern _lcd_dev lcddev;      /* .width/.height/.id —— 本板 800x480，id=0x4384 */
```
- 像素格式 `LTDC_PIXFORMAT_RGB565`，帧缓冲 `LTDC_FRAME_BUF_ADDR = 0xC0000000`。
- 面板 ID 由 `ltdc_panelid_read()` 读取 PG6/PI2/PI7 三个 ID 脚：本板实测 **0x4384 → 4.3" 800×480**，时序参数由 `ltdc_init()` 自动选表。
- 字模糊背景用全局 `g_back_color`，**默认值 `0xFFFFFFFF` 不是合法 RGB565**，绘制前必须设成 `0x0000` 等有效颜色。

### 3.3 QSPI NOR（`norflash.h`）
```c
void norflash_init(void);
uint16_t norflash_read_id(void);          /* 本板实测 0xEF17 = W25Q128 */
void norflash_read(uint8_t *pbuf, uint32_t addr, uint32_t len);
void norflash_write(uint8_t *pbuf, uint32_t addr, uint32_t len);   /* 内部先擦后写 */
void norflash_erase_sector(uint32_t saddr);
void norflash_erase_chip(void);
```
地址空间 0~16 MB；扇区 4 KB。**不要**把参数/校准数据放在 0 区（自检使用 8 MB 偏移处）。

### 3.4 SD 卡（`sdmmc_sdcard.h`）
```c
uint8_t sd_init(void);                       /* 0 = 成功 */
uint8_t get_sd_card_info(HAL_SD_CardInfoTypeDef *info);
uint8_t get_sd_card_state(void);
uint8_t sd_read_disk(uint8_t *pbuf, uint32_t saddr, uint32_t cnt);
uint8_t sd_write_disk(uint8_t *pbuf, uint32_t saddr, uint32_t cnt);
```
总线位宽由 `SD_BOARD_BUS4` 控制（默认 **1 = 4-bit**）。
实测（15.8 GB SDHC，4-bit）：

| SDMMC_CK | 实测吞吐 | 结果 |
|---|---|---|
| 6 MHz (div=20) | 2.7 MB/s | OK |
| 15 MHz (div=8) | 6.5 MB/s | OK |
| **30 MHz (div=4)** | **11.8 MB/s** | OK（默认） |
| 30 MHz 跨区压力 32×8 KB | 10.3 MB/s | 0 错误 |

`selftest.c` 会在启动时自动扫这三档并选用最快可用档。

### 3.5 FATFS（`Middlewares/FATFS`）

- 版本：ChaN FatFs **R0.14b**（取自开发板例程 `实验28 FATFS实验`，内核 `ff.c/ff.h/ffunicode.c` 未改）
- 本项目配置（`source/ffconf.h`）：
  `FF_USE_LFN=1`、`FF_CODE_PAGE=437`、`FF_FS_EXFAT=1`、`FF_VOLUMES=2`、`FF_USE_MKFS=1`
  → 相比厂商默认（`LFN=3` + `CP936`）**省掉约 175 KB 的 GB2312 码表**；实测链接后只增加约 15.5 KB 代码
- 卷分配：`0:` = SD 卡（4-bit @30 MHz）　`1:` = QSPI NOR 前 9 MB（512 B 扇区，尚未格式化）
- 平台层：`source/diskio.c`（自研）、`source/ffsystem.c`（`malloc/free` + `get_fattime()->0`）

与例程 `diskio.c` 的差异（都是必须改的坑）：

| 问题 | 例程行为 | 本项目 |
|---|---|---|
| SD 读写失败 | `while (res) { sd_init(); ... }` **死循环** | 最多重试 3 次后返回 `RES_ERROR` |
| `disk_ioctl` | 只返回 `RES_OK`，**不回填 `buff`** → 容量/`f_mkfs` 全错 | 正确回填 `GET_SECTOR_COUNT/SECTOR_SIZE/BLOCK_SIZE` |
| 内存依赖 | 依赖厂商 `MALLOC` 中间件（`mymalloc(SRAMIN,…)`） | 直接用 C 库 `malloc/free` |
| 时间戳 | — | `get_fattime()` 返回 0（无 RTC） |

用法：
```c
FATFS fs; FIL f; UINT br;
f_mount(&fs, "0:", 1);                                  /* 挂载 SD 卷 */
if (f_open(&f, "0:/TEXT/a.txt", FA_READ) == FR_OK) {
    f_read(&f, buf, sizeof(buf), &br);
    f_close(&f);
}
```

---

## 4. 自检程序（`User/selftest.c`）

上电自动执行 5 项测试，串口 + 屏幕双通道输出：

| 项 | 判据（实测值） |
|---|---|
| SDRAM | 32 MB × 2048 个 16 KB 检查点 + 64 KB × 5 种图样，**0 错误** |
| LCD | 面板 ID `0x4384`、`800×480`；像素回读 `0xF800` 一致（帧缓冲在 SDRAM） |
| QSPI | ID `0xEF17`；8 MB 处 4 KB 写入→回读 **0 失配** |
| SD | 15801 MB SDHC；三档时钟扫描 + 32×8 KB 跨区压力，**0 错误**，MBR 签名 `55AA` |
| FATFS | 挂载 `0:` 成功；FAT32 15784 MB / 空闲 15783 MB；根目录列举；读 `PAINT/*.bmp` 成功；512 B 写→读校验→删除 全通过 |

串口 115200，输出形如：
```
RESULT SDRAM=PASS LCD=PASS QSPI=PASS SD=PASS FATFS=PASS
```

---

## 5. 移植中遇到的问题与处理（重要）

### 5.1 SD 卡 4-bit：**触点脏污导致 DAT 通道失效**（已解决）
- 现象：`HAL_SD_Init` 成功、能读容量（15801 MB），但 `HAL_SD_ReadBlocks` 在 30/15/6 MHz 下**全部数据超时**（`ErrorCode=0x80000000`）。
- 判断依据：CMD 通路正常（CID/CSD/容量可读）→ 问题在 **DAT1~DAT3 数据通路**。
- 处理：**清洁 SD 卡座触点后重测**，4-bit 三档全部通过，30 MHz 达 11.8 MB/s。
- 结论：这是**接触问题**，不是软件问题，也不需要格式化卡。
- 代码里保留位宽开关（默认 4-bit）：
```c
/* Drivers/BSP/SDMMC/sdmmc_sdcard.h */
#define SD_BOARD_BUS4  1   /* 0 = 退回 1-bit（触点再次劣化时的应急选项） */
```
- 排查经验：若再次出现「能读容量、读块超时」→ 先查触点/换卡，再考虑降速。

### 5.2 厂商 `sd_read_disk()` 会死等
`while (get_sd_card_state() != SD_TRANSFER_OK)` 里超时分支只赋值不 `break`，卡异常时**永久挂起**。
本项目自检改为直接调用 `HAL_SD_ReadBlocks()` + 自带超时守卫。

### 5.3 `MemManage_Handler` 重复定义
`mpu.c` 与 `stm32h7xx_it.c` 都定义了该中断。处理：删除 `mpu.c` 中的定义（保留 `it.c` 的标准实现），已备份原文件。

### 5.4 `SDMMC_INIT_CLK_DIV` 需按板级时钟修正
厂商要求在 `stm32h7xx_ll_sdmmc.h` 中把 `0xFA` 改为 `0x12C`（240 MHz 内核时钟下得到 400 kHz 初始化时钟）。已按厂商值修改并备份。

### 5.5 SDRAM 被配置为 CACHEABLE+BUFFERABLE，LTDC/DMA2D 不参与 Cache
CPU 画完必须把脏行写回，否则 DMA/LTDC 读到旧数据：
```c
SCB_CleanDCache_by_Addr((uint32_t*)0xC0000000, 800*480*2);   /* 写回 */
SCB_InvalidateDCache_by_Addr(...);                           /* DMA 写后丢弃 */
```
`selftest.c` 里对每次 DMA2D 填充做了 clean-before / invalidate-after 的封装（`fb_fill()`/`fb_clear()`）。
> 后续接入 TGX 软件渲染时，这是必须保留的约定（或把 SDRAM 区域改成 non-cacheable）。

### 5.6 板载 CH340 的 DTR/RTS 接 BOOT0/NRST（实验记录，**务必注意**）
- `DtrEnable=$false` → BOOT0 拉高 → 复位后进入**系统 Bootloader**（PC 停在 `0x1FF0xxxx`），应用不运行；
- `DtrEnable=$true`、`RtsEnable=$false` → 正常从 Flash 启动；脉冲 RTS 即可复位运行。
- 串口脚本（`DSH/middleware/serial_capture.ps1`）固定 DTR=1 / RTS=0，并提供 `-Reset` 自动复位。

---

## 6. 构建 / 烧写 / 验证流程

```bash
# 1) 构建（uVision 批处理，输出 Output/STM32H743.axf）
/d/MDK5/UV4/UV4.exe -b Projects/MDK-ARM/STM32H743.uvprojx -j0 -o build.log

# 2) 烧写（OpenOCD + ST-Link）
bash DSH/middleware/flash.sh

# 3) 复位并抓串口（COM11）
powershell -File DSH/middleware/serial_capture.ps1 -Seconds 25 -Out boot.log -Reset

# 4) 只读核对：把 SDRAM 帧缓冲导出成 PNG（无需串口）
#    openocd: dump_image fb.raw 0xc0000000 768000
python DSH/middleware/rgb565_to_png.py fb.raw screen.png 800 480
```

工程文件改动由脚本维护：`DSH/middleware/patch_uvprojx.py`（新增源组/HAL 模块，幂等，可重复执行）。

---

## 7. 已知限制 / 后续

| 项 | 状态 |
|---|---|
| SD 4-bit | ✅ 可用（30 MHz / 11.8 MB/s）；触点脏污会退化为读块超时，先清洁/换卡 |
| FATFS 文件系统 | ✅ 已加入（R0.14b，SD 卷可读可写）；QSPI 卷 `1:` 接口已就绪但**未格式化**（需要时调 `f_mkfs("1:", …)`） |
| 触摸（GT1151Q） | 未移植（非本次目标） |
| 帧缓冲 | 单缓冲；接 Spine 渲染时需要双缓冲 + LTDC 换页 |
| 编译器 | 当前 AC5（纯 C 驱动）。接 Spine/TGX 时需切 AC6 + `-std=c++1z` |

---

## 8. 源码编码约定（统一 UTF-8 无 BOM）

| 项 | 约定 |
|---|---|
| 编码 | **UTF-8，不带 BOM** |
| 范围 | `Drivers/`、`Middlewares/`、`User/`、`Projects/` 全部源码（本轮转换 31 个 GBK 文件，现共 308 个文件全部为 UTF-8） |
| 备份 | 转换前的原始文件在 `save/26-11-15-09-43/`（保留原目录结构） |
| 脚本 | `DSH/middleware/convert_to_utf8.py`（幂等：已是 UTF-8 的文件自动跳过；支持 `--dry-run`） |

**为什么不用 BOM**：ARM Compiler 5 的汇编器 `armasm` 遇到 UTF-8 BOM 直接报
`A1167F: Invalid line start`（`startup_stm32h743xx.s` 编译不过）。AC5/AC6 的 C 编译器本身都能接受 BOM，但为统一，全部不写 BOM。

**为什么转换是零风险的**：实测这 31 个文件里的非 ASCII 字符**全部位于注释中**，字符串字面量里 0 处非 ASCII
（扫描结果：`string literals containing non-ASCII: 0`）。因此转换不改变固件生成的任何字节，只影响源码可读性。
附带好处：GBK 的部分汉字第二字节是 `0x5C`（反斜杠），在行尾会引发续行问题；UTF-8 不存在该隐患。

**uVision 显示乱码时**：`Edit → Configuration → Editor → Encoding` 选 **UTF-8**（全局一次性设置）。
uVision 默认是 ANSI(GBK)，不设置的话打开 UTF-8 文件会显示乱码。

**第三方库不动**：`thirdPartyComponents/`（spine-c、tgx-main）保持上游原样——其中 813 个文件本来就是 UTF-8，
另有 4 个是上游自带的 BOM，属于上游产物，不做修改。
