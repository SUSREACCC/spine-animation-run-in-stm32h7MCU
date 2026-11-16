# 执行日志（project = D:\WorkSpace\MDK\H7spineRuntimeTest）

> 规则：每轮「对话-执行」结束后追加一条简报（时间 + 做了什么 + 结论/产出 + 下一步）。

---

## 2026-11-14 15:40 — 阶段 0：Spine × STM32H743 × TGX 技术可行性评估

**任务**：评估在 STM32H743IIT6 + LTDC RGB 屏上移植 Spine 运行时（配合 TGX 图形库）播放骨骼动画的技术可行性，输出报告。

**性质**：只读侦察 + 工具链实机验证。**未修改任何项目源文件**（故未触发 save 备份）。

### 做了什么

1. 读取 `DSH/rules.md`（6 条项目规则）与现有工程结构：`Drivers/BSP` 为空、`Middlewares` 为空、`Projects/MDK-ARM/STM32H743.uvprojx` 为 LED 模板。
2. 硬件基线：从板级手册 PDF（`1. 用户手册`）与例程 `实验12 LTDC_RGB并口屏显示实验` 核实
   → H743IIT6@480MHz、DP-FPU、1MB SRAM、2MB Flash、16MB QSPI、**32MB SDRAM@0xC0000000**、LTDC RGB565、模块 800×480。
3. 组件审查：
   - `tgx-main` 1.1.4：纯 C++17、无外部依赖、有 STM32H7 专用配置分支；`drawTexturedGradientTriangle` 正好满足 Spine 渲染需求。
   - `spine-c` 4.3：**发现其为 spine-cpp 的 C-API 包装层**，`src/generated/*.cpp` 全部依赖 `<spine/spine.h>`，
     而项目内**缺少 spine-cpp** —— 唯一硬阻塞项。与上游 4.3 分支逐文件比对，仅 14 个非代码文件不同 → 直接取 4.3 分支 spine-cpp 即可。
4. 用真实工具链验证（`D:\MDK5\ARM\ARMCLANG` = **AC6.7 / MDK 5.24**）：
   - `-std=c++17` 不被支持，`-std=c++1z` 可用；
   - TGX 纹理三角形 TU：0 error，代码 3,288 B；
   - spine-cpp(88) + spine-c 生成层(134) + extensions = ~223 文件：**0 error**（`-fno-exceptions -fno-rtti`）；
   - 全量链接：**RO 302 KB / RW 124 B**，最大占用 SkeletonJson 52KB、SkeletonBinary 46KB；
   - 仅需 2 个极小兼容补丁：`strdup`（ARM C 库缺失，自实现 ~10 行）、`abs(int)` 二义（`-include <stdlib.h>`）。
5. 产出文档与可复现探针（见下）。

### 产出

| 文件 | 说明 |
|---|---|
| `DSH/spine-porting-feasibility.md` | 可行性报告（结论/硬件基线/组件评估/实测证据/架构/工作项/风险/预算/待确认/分阶段计划） |
| `DSH/middleware/ac6-probe/README.md` | 探针复现步骤与实测数据 |
| `DSH/middleware/ac6-probe/run_probe.sh` | 一键“编译+链接+体积统计”脚本 |
| `DSH/middleware/ac6-probe/fix_stdlib.h` / `compat.h` / `spine_compat.c` | 两个兼容补丁（不改第三方源码） |
| `DSH/middleware/ac6-probe/tgxprobe2.cpp` / `linkmain.cpp` | TGX 关键路径 / Spine C-API 集成探针 |

### 关键结论

- **可行**；主要不确定性是**渲染帧率尚未实测**（Phase 0 基准，半天可定论）。
- 资源预算宽裕：Flash 295KB/2MB、SDRAM 3–6MB/32MB。
- 工作项合计约 **10.5 人日**。

### 环境副作用（记录在案）

- 本会话 shell 对工作区**子目录**无写权限（目录 ACL 缺少授予项，仅工作区根目录可写），
  故所有落盘改用内置文件工具完成。若后续需要脚本自动构建，需一次权限修复（会弹审批）。
- 探针脚本的下载与编译产物放在 `%TEMP%`（`/tmp`），未污染工程目录。

### 下一步（等待用户指令）

按报告 §9 的 Q1–Q6 确认（屏幕型号 / Spine 授权与资产 / 是否升级 MDK / 目标帧率 / 是否允许拉取 spine-cpp / 特性范围），
确认后即可按 Phase 0（基准）→ Phase 1（渲染骨架）推进。

---

## 2026-11-14 16:05 — 阶段 0（续）：报告 V2 修订 —— 用户决策落地 + 本地 spine-cpp 复核

**触发**：用户确认 6 项决策（4.3" RGB 屏 / 已有 Spine 4.3 授权 / 动画尺寸未定 / 沿用当前 MDK / 帧率需实测 / 本地 spine-cpp 在 `D:\gitCode\spine_runtimes`），并要求完善报告。

**性质**：只读复核 + 用**用户实际代码**重跑编译链接。未修改任何项目源文件。

### 做了什么

1. 核实本地 `D:\gitCode\spine_runtimes`：git 检出，branch `4.3`，HEAD `405f4329`（2026-11-10），`spine-cpp` 版本宏 4.3，88 个 .cpp / 113 个 .h，`throw|dynamic_cast|typeid` 共 0 处。
2. **版本配对结论反转**：`diff -rq` 工程内 `thirdPartyComponents/spine-c` 与本地 git `spine-c` → **0 差异（逐字节一致）**。
   ⇒ V1 的“缺 spine-cpp”“版本漂移”两个风险**消除**。
3. 用本地代码重跑探针（`run_probe.sh /d/gitCode/spine_runtimes`）：**227 文件 / 0 error**。
4. 修正 V1 的体积数据：`armlink` 默认移除未引用段 →
   `-std` 走 `.skel` 路径时 **RO 205 KB**（V1 写的 295 KB 是中间态数据）；`--no_remove` 全保留 **381 KB**。
5. 用模板诊断技巧提取 ARM 32-bit 下 spine 关键结构体 sizeof（BoneData 160 / SlotData 128 / MeshAttachment 188 /
   SkeletonData 224 / IkConstraint 92 …），据此建立 §6 内存模型。
6. 核实 4.3" 屏规格：**WKS43WV067-WCT，4.3" IPS，800(RGB)×480，16/24-bit RGB 接口，CTP=GT1151Q(I²C)**。
7. 核实首期必需特性：IK / 网格变形 / 裁剪蒙版 在 spine-cpp 内已实现，且 spine-c 已生成对应 C API
   （`ik_constraint.h` / `deform_timeline.h` / `mesh_attachment.h` / `clipping_attachment.h` 均在）。
8. 重写报告：新增 §1 决策表、§4 实测证据（含方法论）、§5 特性覆盖矩阵、§6 内存模型、
   §8 性能评估方案（基准协议 + 决策表 + 优化阶梯）、§12 剩余确认项、附录 C 边界声明。

### 产出

| 文件 | 变更 |
|---|---|
| `DSH/spine-porting-feasibility.md` | **重写为 V2** |
| `DSH/middleware/ac6-probe/README.md` | 更新数据（227 文件 / 205 KB / 381 KB / sizeof 表 / 版本配对） |
| `DSH/middleware/.probe` | 已清理 |

### 关键结论（V2）

- **可行，且主要不确定性已消除**：版本配对 0 差异、227 文件 0 error、RO 205 KB。
- 首期三项特性（IK/变形/裁剪）**不增加运行时开发量**，只增加验证工作量（W7 1 人日）。
- 工作项合计 **≈ 10.75 人日**。
- 唯一实质风险仍是**渲染吞吐未实测** → 已在报告 §8 给出可复现基准协议（B1–B6）与查表决策法。

### 下一步（等待用户指令）

Phase 0（0.5 天）：板级例程 → SDRAM/LTDC → TGX 纹理三角形 → 按 B1–B6 测吞吐。
执行前会提交 Phase 0 计划简报（含要新增/修改的文件清单与 `save/` 备份方案）等待确认。
仍需用户提供的素材：一份 Spine 4.3 导出的 `.skel` + `.atlas` + PNG（R1）。

---

## 2026-11-14 16:20–17:05 — 阶段 1：板级驱动移植与验证（SDRAM / LCD / QSPI NOR / SD）

**目标**：依据开发板例程移植四个驱动，并用实际硬件（ST-Link + COM11）验证。

**结果**：**4/4 全通过**
```
RESULT SDRAM=PASS LCD=PASS QSPI=PASS SD=PASS
```

### 做了什么

1. 备份 `User/main.c`、`STM32H743.uvprojx` 到 `save/26-11-14-16-16/`。
2. 从板级例程拷贝 BSP：`MPU`(实验11)、`SDRAM`(11)、`LCD`(12: lcd/ltdc/lcdfont/tft_spi)、`QSPI`+`NORFLASH`(22)、`SDMMC`(27)、`LED`(27)。
3. 工程改造：`DSH/middleware/patch_uvprojx.py` 幂等注入 7 个 BSP 源组 + 14 个 HAL/LL 模块
   （ltdc(_ex)、dma2d、sdram、sram、qspi、mdma、sd(_ex)、dma_ex、tim(_ex)、ll_fmc、ll_sdmmc）。
4. 编写 `User/selftest.c`：上电跑 4 项测试，串口 + 屏幕双通道输出，末尾心跳。
5. 打通验证链路：`UV4 -b` 构建 → `OpenOCD` 烧写 → `serial_capture.ps1` 抓 COM11 →
   另加一条**不依赖串口**的证据链：SWD 直接 dump SDRAM 帧缓冲 → Python 转 PNG 肉眼核对。

### 关键问题与根因（都已解决）

| # | 现象 | 根因 | 处理 |
|---|---|---|---|
| 1 | 串口完全无声，PC 停在 `0x1FF0A97A` | 板载 CH340 的 **DTR/RTS 接 BOOT0/NRST**；脚本把 DTR 拉低 → BOOT0 高 → 进系统 Bootloader | 串口脚本固定 DTR=1 / RTS=0，并支持 `-Reset` 脉冲复位 |
| 2 | SD 读卡死 | 厂商 `sd_read_disk()` 的等待循环超时分支不 `break`，永久挂起 | 自研 `sd_try_read()` 直接调 `HAL_SD_ReadBlocks` + 超时守卫 |
| 3 | SD 4-bit 全超时（30/15/6 MHz） | CMD 通路正常（能读容量 15801 MB），**DAT1~3 不可用** | 默认改 **1-bit @30 MHz**，读扇区成功；头文件留 `SD_BOARD_BUS4` 开关 |
| 4 | 链接报 `MemManage_Handler` 重复定义 | `mpu.c` 与 `stm32h7xx_it.c` 同名中断 | 删 `mpu.c` 中的定义（保留 it.c），已备份 |
| 5 | SD 初始化时钟偏快 | 厂商要求把 `SDMMC_INIT_CLK_DIV` 由 `0xFA` 改 `0x12C` | 已改（`stm32h7xx_ll_sdmmc.h`，已备份） |
| 6 | 屏幕文字背景异色 | 字模用全局 `g_back_color` 填背景，默认 `0xFFFFFFFF` 非合法 RGB565 | 绘制前设 `g_back_color=0x0000` |

### 实测数据

| 项 | 结果 |
|---|---|
| SDRAM | 32 MB / 2048 检查点 / 5 种图样 → **0 错误** |
| LCD | 面板 ID **0x4384**、**800×480**；像素回读 0xF800 一致（帧缓冲 @0xC0000000） |
| QSPI | ID **0xEF17**(W25Q128)；8 MB 处 4 KB 写→读 **0 失配** |
| SD | **15801 MB**、SDHC；扇区 0 读到 `33 C0 8E D0`（MBR 引导码） |
| 构建 | **0 error / 0 warning**，Code 43 KB，ZI 2.06 MB（含 SDRAM 帧缓冲声明） |

### 产出

| 文件 | 说明 |
|---|---|
| `Drivers/BSP/**` | 四个驱动（含依赖的 MPU/LED） |
| `User/selftest.c/.h`、`User/main.c` | 自检固件 |
| `docs/board-drivers.md` | 驱动接口、初始化顺序、6 个坑的处理、构建/烧写/验证流程 |
| `DSH/middleware/patch_uvprojx.py` | 工程文件注入脚本（幂等） |
| `DSH/middleware/flash.sh`、`serial_capture.ps1` | 烧写 / 串口抓取（含 DTR/RTS 极性与自动复位） |
| `DSH/middleware/rgb565_to_png.py`、`screen_final.png` | 帧缓冲 → PNG，屏幕内容客观证据 |
| `save/26-11-14-16-16/` | main.c、uvprojx、sdmmc_sdcard.c、stm32h7xx_ll_sdmmc.h 备份 |

### 下一步

接 Spine 前还差两件事：① 加 FATFS（卡内已有 FAT32 分区）或直接按块读取资源；② 帧缓冲双缓冲 + LTDC 换页。
之后进入 Phase 0 性能基准（见 `DSH/spine-porting-feasibility.md` §8）。

---

## 2026-11-14 17:2x — SD 卡 4-bit 复测（用户清洁触点后）

**触发**：用户清理 SD 卡座引脚触点，要求再次尝试四线（4-bit）驱动。

### 改动

1. `Drivers/BSP/SDMMC/sdmmc_sdcard.h`：`SD_BOARD_BUS4` 由 0 → **1**（回到厂商 4-bit 默认）。
2. `User/selftest.c`：`test_sd()` 重写为**能力扫描**版本
   - 依次测 div=20/8/4 → 6/15/30 MHz，每次读 16 扇区（8 KB）
   - 用 DWT->CYCCNT 计时算吞吐，并校验 MBR 签名 `55 AA`
   - 自动选**最快可用档**，再做 32×8 KB 跨区压力读（覆盖整卡）

### 结果：4-bit 完全恢复，全速通过

| SDMMC_CK | 吞吐 | 结果 |
|---|---|---|
| 6 MHz (div=20) | 2672 KB/s | OK |
| 15 MHz (div=8) | 6495 KB/s | OK |
| **30 MHz (div=4)** | **11762 KB/s** | OK（自动选用） |
| 跨区压力 32×8 KB @30 MHz | 10262 KB/s | 0 错误 |

两次独立复位启动结果一致（差异 <0.5%），MBR 签名 `55AA` 正确。

### 结论

- 之前的「能读容量但读块超时」是**触点接触不良**导致 DAT1~3 失效，不是软件/卡的问题，也不需要格式化。
- 已把该经验写进 `docs/board-drivers.md` §5.1：出现同类现象先清洁/换卡，再考虑降速。
- 代码保留 `SD_BOARD_BUS4` 开关（现为 1），若触点再次劣化可退回 1-bit 应急。

### 产出

- `docs/board-drivers.md` 同步更新（SD 章节、自检表、已知限制）
- `DSH/middleware/patch_sd_sweep.py`：把 test_sd 改成扫描版的补丁脚本
- 串口日志：`DSH/middleware/sd_final.log`、`sd_repeat.log`

---

## 2026-11-14 17:3x–18:0x — FatFs 集成（SD 卷只读 + 写入回环验证）

**目标**：把文件系统打通，为后续从卡里读 Spine 资源（`.skel/.atlas/PNG`）做准备。

**结果：PASS**
```
RESULT SDRAM=PASS LCD=PASS QSPI=PASS SD=PASS FATFS=PASS
```

### 做了什么

1. 从 `实验28 FATFS实验` 拷 ChaN **FatFs R0.14b** 内核（`ff.c/ff.h/ffunicode.c`，未改）到 `Middlewares/FATFS/source/`。
2. `ffconf.h` 精简：`FF_USE_LFN=1`、`FF_CODE_PAGE=437`、`FF_FS_EXFAT=1`、`FF_VOLUMES=2`
   → 相比厂商默认（LFN=3 + GBK936）省掉 **175 KB** GB2312 码表；链接后实测只增加 **+15.5 KB 代码**。
3. 自研 `diskio.c`（卷 0 = SD，卷 1 = QSPI NOR 前 9 MB）与 `ffsystem.c`（`malloc/free`，无 MALLOC 依赖）。
4. 修掉厂商集成层的 3 个问题：
   - `diskio.c` 的 `while (res) { sd_init(); ... }` 失败重试死循环 → 最多 3 次
   - `disk_ioctl` 只回 `RES_OK` 不回填 `buff`（容量/mkfs 会全错）→ 正确回填扇区数/大小/块大小
   - `sd_read_disk()/sd_write_disk()` 内部 `while` 不 break 的永久等待 → 改为有界等待（`patch_sd_bounded.py`）
5. `selftest.c` 增加第 5 项（`[5/5] FATFS`）：挂载 → 容量 → 根目录列举 → **下钻一层读文件** → **512 B 写/读/删回环**。

### 实测输出

```
[5/5] FATFS on SD volume 0:
  volume    : FAT32, total 15784 MB, free 15783 MB
   System Volume Information/  0 B
   PAINT/  0 B
   TEXT/  0 B
  read      : 0:/PAINT/PAINT20241215001314.bmp -> 16 B, 42 4D 42 B8 ...
  entries   : 3 listed, file read OK
  write     : 512 B -> readback match, delete ok
```

- `42 4D` = "BM"，读到的确实是一张 BMP 文件（前 4 字节 `42 4D 42 B8`）
- 写入 512 B → 读回逐字节一致 → 删除成功（卡未被永久改动）

### 工程改动

- `Projects/MDK-ARM/STM32H743.uvprojx`：新增 `Middlewares/FATFS` 源组（`patch_uvprojx.py` 幂等维护）
  ⚠️ 期间一次脚本转义错误把 `\f` 写成换页符导致项目 XML 损坏，已从 `save/` 备份恢复并修正脚本
- 编译：**0 error / 0 warning**，Code 58.6 KB（+15.5 KB），RO 14.1 KB

### 产出

| 文件 | 说明 |
|---|---|
| `Middlewares/FATFS/source/{ff.c,ff.h,ffconf.h,ffunicode.c,diskio.h}` | FatFs 内核（精简配置） |
| `Middlewares/FATFS/source/{diskio.c,ffsystem.c}` | 自研平台层 |
| `User/selftest.c` | 第 5 项 FATFS 测试（含目录下钻与写回环） |
| `DSH/middleware/{patch_add_fatfs_test.py,patch_fatfs_readfile.py,patch_fatfs_write.py,patch_sd_bounded.py}` | 本次改动的可复现脚本 |
| `DSH/middleware/screen_five_pass.png` | 屏幕五项全通过截图 |
| `save/26-11-14-16-16/sdmmc_sdcard.c.before_bounded.bak` | 修改前的 SD 驱动备份 |

### 下一步

资源读取通道已就绪（`f_open`+`f_read` 到 SDRAM）。接下来是 Spine Phase 0：AC6 工程切换 + TGX 编译 +
渲染吞吐基准（`.skel/.atlas` 可直接从 SD 读入 SDRAM，无需再拷贝到 QSPI）。

---

## 2026-11-15 09:43 — 源码编码统一为 UTF-8（无 BOM）

**目标**：消除工程内 GBK/UTF-8 混用（uVision 与外部编辑器里中文注释乱码）。

### 做了什么

1. 全工程扫描（`Drivers/`、`Middlewares/`、`User/`、`Projects/`，308 个源文件）：
   **31 个 GBK**、276 个已是 UTF-8，0 个无法识别。
2. 备份原始文件到 `save/26-11-15-09-43/`（保留目录结构）。
3. 用 `DSH/middleware/convert_to_utf8.py` 批量转 GBK → **UTF-8 无 BOM**。
4. 验证：308/308 文件均可按 UTF-8 解码、**无一个带 BOM**；中文显示正常（抽查 `sdram.c` 头部注释）。
5. 重新编译：**0 error / 0 warning**。

### 关键决策：为什么不写 BOM

实测 ARM Compiler 5 的汇编器 `armasm` 不接受 UTF-8 BOM：
```
"bom.s", line 1: Error: A1167F: Invalid line start
```
而 `startup_stm32h743xx.s` 必须过 armasm，所以统一 **无 BOM**。
（AC5/AC6 的 C 编译器本身能接受 BOM，但为一致性全部不写。）

### 安全性论证

扫描全部 C/H 文件：**字符串字面量中含非 ASCII 的：0 处**。
即这些中文只出现在注释里 → 转换不改变固件生成的任何字节。
附带好处：GBK 某些汉字的第二字节是 `0x5C`（`\`），行尾会造成续行/转义隐患；UTF-8 无此问题。

### 未能完成的部分

转换后想再烧板做一次运行验证，但 **ST-Link 与 CH340（COM11）都已从 Windows 设备列表消失**，
OpenOCD 报 `Error: open failed`（连续 2 次）。判断为板子 USB 被断开/断电，需要用户重新连接后补做。
编译验证不受影响。

### 产出

| 文件 | 说明 |
|---|---|
| `DSH/middleware/convert_to_utf8.py` | 幂等转换脚本（`--dry-run` 预演） |
| `save/26-11-15-09-43/**` | 31 个原始 GBK 文件备份 |
| `docs/board-drivers.md` §8 | 编码约定（含 uVision 设置说明） |

---

## 2026-11-15 10:00 — TGX 2D 子集裁剪移植 + AC6 工程切换 + 首次吞吐实测

**目标**：把 TGX 中 Spine 需要的 2D 组件裁进来，切到 AC6 编译，并做吞吐基准。保留原开屏自检。

### 做了什么

1. **工程切 AC6**（TGX 依赖 C++17，AC5 只到 C++03）：`uAC6=1`、`Optim=2`、`wLevel=1`。
   途中解决 3 个坑（详见 `docs/tgx-port.md` §1）：
   - CMSIS 缺 `cmsis_armclang_ltm.h` → 改 `cmsis_compiler.h` 走 `cmsis_armclang.h`（已备份）
   - uVision 5.24 的 C++ 标准最高 C++14 → 给 .cpp 加**文件级** `-std=c++1z -fno-exceptions -fno-rtti`
   - `<FileOption>` 字段不全导致选项泄漏到汇编器；且 `IncludeInBuild=0` = **排除构建** → 补全 schema 并设 1
2. **裁剪 TGX** 到 `Middlewares/TGX/`（18 文件 ≈1 MB）：保留 Misc/Vec/Box2/Color/Fonts/ShaderParams/
   Shaders/Rasterizer/bseg/Image；去掉 3D（Mesh3D/Renderer3D/Mat4/Box3）与 6 个内置字库（**约 4.3 MB**）。
   自建精简 `tgx.h`，开头 `#include <stdlib.h>` 解决 AC6 下 `abs(int)` 二义。
3. **新增 TGX 自检** `User/tgx_selftest.cpp`：在 5 项开屏自检之后运行，测
   填充率 / 纹理四边形（双线性+alpha）/ 类 Spine 小三角形，结果画屏 + 串口输出。
4. 编译结果：**0 error / 0 warning**，Code 100 KB（TGX 约 +46 KB）。

### 首次实测（已跑通）

| 项目 | 吞吐 | ≈cycles/px |
|---|---|---|
| 纯填充 800×480 | **77.04 Mpx/s** | 6.2 |
| 纹理四边形（RGB32→RGB565，双线性+alpha） | 1.59 Mpx/s | 302 |
| 类 Spine 渐变三角形 | 1.40 Mpx/s | 343 |

**关键发现**：填充率正常，但**纹理路径慢 50 倍**。按 1.4 Mpx/s 折算，60k 像素的角色约 40 ms/帧（≈25 fps），
180k 像素约 120 ms（≈8 fps）→ **当前配置达不到 30 fps 角色动画**，必须先解决纹理路径。

### 未完成

为定位瓶颈临时加了「RGB565/RGB32 × 是否混合」对照矩阵，但**烧写开始失败**：
`Failed to write memory` / `Fail reading CTRL/STAT` / 重连报 `read version failed`（连续多次）。
判断为 ST-Link/USB 链路状态问题（板子需重新插拔或断电重启），按规则 5 停止重试并汇报。

### 产出

| 文件 | 说明 |
|---|---|
| `Middlewares/TGX/**` | 裁剪后的 TGX 2D 子集 + 自定义 `tgx.h` |
| `User/tgx_selftest.cpp / .h` | TGX 渲染自检 + 基准 |
| `docs/tgx-port.md` | 裁剪清单、AC6 切换三个坑、实测数据与后续排查方向 |
| `DSH/middleware/patch_switch_ac6.py`、`patch_cpp_file_options.py`、`patch_add_tgx.py`、`patch_call_tgx.py`、`patch_tgx_matrix.py` | 全部工程改动可复现脚本 |

---

## 2026-11-15 10:20 — TGX 对照矩阵实测（定位纹理路径瓶颈）

### 结果

| 配置 | 吞吐 | ≈cycles/px |
|---|---|---|
| 纯填充 | 77.53 Mpx/s | 6.2 |
| 纹理 565 + 覆盖写 | 2.73 Mpx/s | 176 |
| 纹理 32 + 覆盖写 | 2.03 Mpx/s | 236 |
| 纹理 32 + alpha 混合 | 1.57 Mpx/s | 306 |
| 渐变三角形（类 Spine） | 1.44 Mpx/s | 333 |

### 结论

瓶颈是**双线性采样 + 着色器 ALU**（最裸的纹理四边形已 176 cyc/px，是填充的 28 倍），
不是带宽，也不是 MPU/Cache 属性（AXI 与 DTCM 都已是 cacheable）。

按 1.44 Mpx/s：60k 像素角色 ≈ 42 ms（24 fps），180k ≈ 125 ms（8 fps）→ 当前达不到 30 fps。

### 后续优化候选（写进 docs/tgx-port.md §6）

降分辨率 / 脏矩形 / 自写点采样光栅器（目标 30–50 cyc/px）/ RGB565 纹理 / 纹理放 DTCM。

### 阻塞

为验证"纹理放 8 KB 能否整块命中 D-Cache"写了探针（`patch_tgx_cache_probe.py`），但**烧写连续失败**：
`Failed to write memory` → `Fail reading CTRL/STAT` → 之后 `read version failed`（1 MHz 也失败，
两种 openocd transport 都试过）。设备管理器中 ST-Link 与 CH340 均为 "OK"，判断为 ST-Link 固件级卡死，
需拔插 USB。已记录到 docs/tgx-port.md §7（含"烧写时保持串口打开"的经验）。

---

## 2026-11-15 11:00 — 点采样改造 + 栈溢出 bug 修复 + 最终数据

### 点采样（新增宏开关，可回退）

`patch_tgx_point_sampling.py` 给 2D 纹理着色器加 `TGX_TEXTURE_POINT` 分支（最近邻取色）：

| 配置 | 双线性 | 点采样 | 提升 |
|---|---|---|---|
| 565 + 覆盖写 | 2.73 Mpx/s | **4.69** | +72% |
| 32 + 覆盖写 | 2.03 | 3.65 | +80% |
| 32 + 混合 | 1.57 | 2.49 | +59% |
| 渐变三角（类 Spine） | 1.44 | **2.07** | +44% |

8 KB 纹理（全驻 D-Cache）与 32 KB 吞吐一致（4.68 vs 4.69）→ 确认瓶颈是 ALU，不是 Cache。

### 重大 bug：栈只有 2 KB（已修）

现象：TGX 图形正常，但**屏幕文字与 DMA2D 填充静默失效**。
定位：SWD 直接读 `lcddev`/`lcdltdc`，发现结构体被垃圾覆盖；查 map 发现栈（2 KB）紧邻这些全局变量，
TGX 模板深调用链溢出，冲掉 LCD 状态。
修复：`startup_stm32h743xx.s` 的 `Stack_Size` 0x800 → **0x4000 (16 KB)**，已备份。
影响：接入 spine-cpp 时调用更深，此问题必须先解决，提前暴露很有价值。

### 最终数据（点采样 + 16 KB 栈）

fill 77.14 Mpx/s，texquad 2.49，tris 2.07 → 60k 覆盖像素 ≈29 ms（34 fps），180k ≈87 ms（11 fps）。

### 产出

- `DSH/middleware/patch_tgx_point_sampling.py`（可回退的着色器改造）
- `DSH/middleware/screen_tgx_final.png`（最终屏幕证据）
- `docs/tgx-port.md` §8–§11（点采样对比、栈 bug 复盘、给 Spine 的建议）
- 备份：`save/26-11-15-09-43/startup_stm32h743xx.s.bak`

---

## 2026-11-15 12:00 — 自写光栅器最小原型验证（回答"成本 vs 收益"）

### 实现

`User/raster_probe.cpp`（约 200 行）：扫描线光栅 + 平面梯度 UV + POT 取模 + 3 种模式
（覆盖写 / 色键 / 色键+常量色调）。精简：无裁剪、无 top-left 规则 → 测得值视为上限。

### 实测（同帧缓冲，AC6 -O2，点采样）

| 负载 | TGX | 自写 | 倍数 |
|---|---|---|---|
| 全屏四边形 覆盖写 | 4.69 | **33.96 Mpx/s** | 7.2× |
| 全屏四边形 色键 | — | 28.82 | — |
| 全屏四边形 色键+色调 | — | 21.26 | — |
| 16×12 网格 色键 | 2.07 | **20.27** | 9.8× |
| 16×12 网格 色键+色调 | — | **15.29** | 7.4× |

cyc/px：覆盖 14.1；色键 16.7；色键+色调 22.6；网格 23.7 / 31.4。

帧率（15.29 Mpx/s）：60k=3.9 ms(250fps) / 180k=11.8 ms(85fps) / 384k=25 ms(40fps)。

### 结论

- 原估算 8–12× 提升 → 实测 **7.4–9.8×**，成立
- 核心循环不难（原型 40 分钟含工程接线），真正的 3–4 人日在**正确性**：
  top-left 边界规则、裁剪、逐顶点色调、4 种混合模式、纹理格式/PMA、像素级回归
- 生产版预期 12–16 Mpx/s

### 工程侧副产品

修掉了工程文件的两个坑：
1. `patch_cpp_file_options.py` 的正则跨块匹配，把 FileOption 塞进了 delay.c/sys.c → 新增
   `clean_file_options.py`（只保留 .cpp 的 FileOption）与 `rebuild_cpp_entries.py`（整块重建，确定性）
2. 模板里 `IncludeInBuild` 必须为 1，为 0 时文件被排除出构建

### 产出

- `User/raster_probe.cpp / .h`（原型 + 基准）
- `DSH/middleware/screen_raster.png`（屏幕：TGX 与自写光栅数字并列）
- `docs/tgx-port.md` §12

---

## 2026-11-15 13:30 — 生产版光栅器 raster2d（功能完整 / 性能待优化）

### 实现

`Middlewares/RASTER/raster2d.{h,cpp}`（~500 行）+ `User/raster_test.cpp`（回归 + 基准）：
定点边界函数 + top-left 规则、任意顶点出屏裁剪、逐顶点 ARGB 色调、4 种混合、
3 种纹理格式（RGB565色键/ARGB1555/ARGB4444）、POT 掩码、Spine 风格 mesh 接口。

**回归 5/5 通过**（覆盖完整性、无接缝、裁剪、色调单调、混合数值）。

### 性能未达标

| 负载 | 生产版 | 原型 | TGX 点采样 |
|---|---|---|---|
| 四边形 覆盖写 | 8.2 | 20.3 | 4.69 |
| 四边形 逐顶点色 | 2.9 | — | — |
| 四边形 4444+色 | 1.5 | — | 2.49 |
| 网格 逐顶点色 | 2.8 | 15.3 | 2.07 |

即：功能完整，但只有原型的 1/5–1/10；混合路径甚至慢于 TGX。

### 已修的两个 bug

1. 边界函数每像素步进漏乘 SUBPIXEL_ONE（16）→ 覆盖全乱（T3 画满整屏）
2. top-left 判定方向写反 → 接缝/重复混合（T2）

### 定位结论

瓶颈在内层循环结构，不在算法：同一算法在原型（扫描线区间、无逐像素判定）能到 15–34 Mpx/s。

### 下一步

内层改扫描线区间（去掉逐像素边界测试）+ 混合去分支 + 三组对照二分定位。

---

## 2026-11-15 15:00 — raster2d 三轮优化（扫描线 / 强制内联 / -O3）

### 效果

| 负载 | 初版 | 扫描线 | +always_inline | +O3 | TGX |
|---|---|---|---|---|---|
| 四边形覆盖写 | 8.2 | 24.8 | 25.0 | **27.7** | 4.69 |
| 网格 565 色调 | 2.8 | 2.0 | 5.05 | **5.50** | — |
| 网格 4444 色调 | 1.4 | 1.54 | 3.41 | **3.56** | 2.07 |

回归 5/5 保持通过。

### 关键发现

1. 逐像素边界判定是主要开销 → 改扫描线区间（端点用定点边函数校验），覆盖写提速 3 倍。
   浮点区间会偏窄 1–2px，必须向外扩展，否则出现 13px 接缝（已修）。
2. 反汇编发现 `mul255`/`pack565` 是外部函数调用（每像素 4–6 次 BL）→ 加 `always_inline`，
   色调路径 2.2 → 5.8 Mpx/s。
3. -O3 再提升 5–10%。

### 结论

覆盖写 27.7 Mpx/s 已超原型；瓶颈集中在"逐顶点色调 + ARGB4444 解包 + 8bit 往返"。
典型 60k 像素角色 17ms（59fps）满足；180k 全身 51ms（20fps）不足。
下一步：色调 16.16 定点化、565 原生混合、或离线预乘 tint。

---

## 2026-11-15 16:00 — 565 原生混合 + 三档色调

### 实现

- `lerp565()`：NORMAL 混合在 RGB565 空间逐通道 lerp，省掉 unpack dst / pack 回写
- `add565()`：565 原生饱和加
- COLMODE 三档：0=常量色 / 1=RGB恒定仅alpha变化（spine slot alpha）/ 2=完整逐顶点

### 实测（-O3）

| 负载 | 结果 |
|---|---|
| 四边形 常量色调 | **9.13 Mpx/s** |
| 四边形 仅alpha(4444) | **4.44** |
| 网格 仅alpha(4444) | **4.15** |
| 网格 完整逐顶点(4444) | 3.45 |
| 四边形 覆盖写 | 27.8 |

回归 5/5 通过。

### 结论

565 原生混合主要利好"常量色调"路径（9.1）；完整逐顶点几乎无改善——
瓶颈是 ARGB4444 解包(3×17) + 通道插值 + 钳位，占了三分之二。

### 下一步最大杠杆

离线预乘 tint（退化成覆盖写，3–5×）或改用 ARGB1555 纹理（+25–40%）。

---

## 2026-11-15 17:00 — ARGB1555 实测（素材可控，采纳该格式）

### 结果

| 负载 | 4444 | **1555** | 提升 |
|---|---|---|---|
| 网格 逐顶点 | 3.46 | **6.82 Mpx/s** | 1.97× |
| 四边形 常量色调 | 4.44 | **11.20** | 2.5× |
| 覆盖写 | 27.8 | 27.8 | — |

帧率（6.82）：60k=8.8ms(114fps) / 180k=26.4ms(38fps) / 240k=35ms(28fps)。

### 结论

换成 ARGB1555 后 180k 全身角色从 20fps 提升到 38fps，达到目标。
raster2d 的 fmt 是逐纹理参数，可混用：硬边用 1555、柔边用 4444、全不透明用 RGB565+色键。

回归 5/5 保持通过；屏幕显示 R2D 6.82 Mpx/s (prod, ARGB1555)。

---

## 2026-11-15 18:30 — Spine 4.3 代码集成

### 完成

- `Middlewares/SPINE`：spine-cpp 4.3 全部 88 个源文件编译通过（0 error）
- `User/spine_platform.cpp`：SDRAM 分配器（8 MB 池）+ getDefaultExtension + FatFs _readFile
- `User/spine_test.cpp`：Atlas + SkeletonBinary + AnimationState + SkeletonRenderer → raster_mesh
- `DSH/middleware/png_to_argb1555.py`：PNG→ARGB1555 转换器（纯 python，zlib 解 PNG）
- spineboy 素材已转换到 `spine_assets/`

### 两个坑

1. `__stdout` 冲突：spine printf 拉入 stdio_streams.o。方案=保留自己的 __stdout + 编译掉 printUpdateCache 的 printf
2. 静态初始化早于 SDRAM：全局 extension 构造时写 SDRAM 导致上电无输出 → 改惰性构造

### 状态

板子跑通到加载阶段：`[SPN] atlas load FAILED (/spine/spineboy-pma.atlas)`（素材未拷入 SD）。
代码 581 KB / Flash 2 MB。

### 下一步

等待素材拷入 SD 卡 → 验证渲染 + 测帧率。

---

## 2026-11-15 14:15 — Spine 板级跑通（spineboy 正确渲染）

### 结果

spineboy-pro（67 骨骼/52 槽位/11 动画）正确渲染：**20.19 ms/帧 = 49.5 fps**，
30 条渲染命令 / 8280 顶点，纹理 1024x256 ARGB1555，spine 堆 417 KB 无失败，代码 582 KB。

### 定位的 4 个 bug

1. 上电无输出：全局 extension 构造早于 SDRAM 初始化 → 改惰性构造
2. __stdout 重复定义 / _sys_open：spine printf 拉入 stdio_streams.o → 保留自己的 __stdout + 编译掉 printUpdateCache
3. 角色上下颠倒：spineboy-pro 世界 Y 向下 → 直通映射 + 包围盒拟合
4. **颜色全错且改解码无效**：RAW_COPY 快路径把 ARGB1555 原始 texel 直写进 RGB565 帧缓冲
   → dispatch_color 加 FMT==0 守卫

### 关键教训

RAW_COPY（"直接写纹理原值"）只在源与目标格式相同时成立；加入新纹理格式时必须检查所有快路径。

### 素材

/spine/ 下三个文件；固件支持 /spine/ 与根目录两种放法（路径回退）。
/spineboy-pma.raw 用 png_to_argb1555.py --pma 生成（反预乘 + alpha 阈值 128）。

---

## 2026-11-15 14:40 — spineboy 动画验证

### 11 个动画

aim, death, hoverboard, idle, idle-turn, jump, portal, run, run-to-idle, shoot, walk

（示例 .skel 自带，无需下载）

### 动画总览

`spine_anim_sheet()`：每个动画取 t=0.45s 姿态渲染到 4x3 网格，一次 dump 看全部。
11 格共 94.8 ms（平均 8.6 ms/角色）。

### 运动校验

同 clip（run）两个时间点比较单元格校验和：t0=C3BBFF7A vs t1=F72A5703 → MOVING，
证明 AnimationState 时间推进 + apply + updateWorldTransform(Physics) 均正常。

### 产出

- `DSH/middleware/screen_spine_anims.png`（11 动画总览）
- `docs/spine-integration.md` 增补动画验证章节

---

## 2026-11-15 15:10 — walk 动画实时播放（双缓冲）

### 实现

`spine_play(skel, atlas, anim, fps, seconds)`：
- 双缓冲（前台 0xC0000000 / 后台 0xC1A00000），渲染完后台后写 CFBAR + SRCR=VBR，
  垂直回扫切换 → 无撕裂
- 固定 dt = 1/fps，不足一帧用 delay_ms 补齐
- 每秒打印 avg/min/max 帧时间

### 实测（walk，30fps，20 秒）

- 稳态 **30.8 fps**（avg 32.4 ms）
- 纯渲染 20.1–24.4 ms，余量 9–13 ms
- 播放结束后两块缓冲各有一帧不同姿势，逐像素差 42535/384000 (11.1%) → 确认在动

### 帧率上限

角色 ~75k 像素/帧，实测 20–24 ms → 30fps 有余量，60fps 达不到（需缩小角色或更快混合路径）。

---

## 2026-11-15 16:20 — 顶点变换 + 混合路径优化（60fps 达成）

### 拆解与结果

| 阶段 | 前 | 后 | 手段 |
|---|---|---|---|
| 清屏 | ~5.0 ms | **1.75 ms** | 局部清屏（bbox 占屏 32%） |
| 绘制 | ~19.0 ms | **14.3 ms** | ARGB1555 565 原生快路径 |
| 单帧 | 20–24 ms | **16.85 ms** | |
| 帧率 | 30 fps | **59.4 fps** | |

### 关键发现

- **顶点变换不是瓶颈**：8280 顶点 ≈ 0.12 ms，占 0.7%。优化它没意义。
- 真正成本在逐像素光栅：2760 个小三角形（平均 25 px/三角形），
  每三角形 ~400 cycles setup ≈ 2.3 ms，其余 ~12 ms 是像素开销。
- 1555 白 tint + 不透明走纯位重组（无 8bit 往返），是最大的一笔（19 → 14.3）。

### 清理

- 去掉 selftest.c 里 while(1) 之后的重复死代码
- 播放前对两块缓冲各全清一次，之后只清 bbox

---

## 2026-11-15 17:00 — 修复播放时的残影/闪烁

### 根因

1. **脏矩形只算一次**：来自 setup pose 包围盒，动画中手臂甩出范围后旧像素永不清 → 残影
2. **双缓冲 2 帧延迟**：缓冲区 X 存的是 N-2 帧的画面，清"当前+上一帧"的并集不够 →
   改为**按缓冲分别记录上一帧包围盒**（pbx[2]/parity）

### 闪烁的成因

残影区域在两块缓冲里内容不同（A 留旧手臂、B 已清背景），LTDC 交替扫描 →
该区域以 30Hz 跳变 → 肉眼即"闪烁"。残影与闪烁是同一 bug。

### 量化

暂停时对比两块缓冲在角色框外的差异像素：
- 固定脏矩形：成片残影
- 当前+上一帧并集：**740 px**（x542–566, y330–381，正是手臂/枪）
- 按缓冲分别记录：**0 px** ✅

### 性能

59.8 fps，清屏 2.2 ms / 绘制 13.6 ms / 单帧 16.7 ms。

### 隐患

60fps 预算余量仅 0.6 ms，偶发超时会重复一帧（judder）。

---

## 2026-11-15 18:00 — 闪烁根因：往显示中的缓冲里画 → 改三缓冲

### 症状

残影修复后仍有"纵向黑色区域在人物上闪烁"。竖条 = 脏矩形，黑色 = 清屏色 0x0861。

### 根因

`LTDC->SRCR = VBR` 只是请求在下一 vblank 切换；切换前旧前台仍在扫描显示，
而双缓冲代码此时已经开始往里清屏+绘制。绘制 13.6ms / 帧 16.7ms ⇒ 81% 时间在写显示中的缓冲。

### 修复

三缓冲：画的那块永远不是正在显示、也不是待切换的；每块各自维护脏矩形（3 帧延迟）。
每帧切换前 `while (LTDC->SRCR & VBR)` 等上次切换完成。

### 验证

暂停时 dump 三块缓冲，角色区非背景占比 29.4% / 29.2% / 28.8% —— 全部完整帧。

### 性能

59.6 fps，clear 1.6ms / draw 13.6ms，余量约 1.4ms。

---

## 2026-11-15 19:00 — 三角形 setup 定点化

### 改动

包围盒/绕序/边 x(y)/行跨度 全部改定点；边斜率用一次浮点除法 + 16.16 增量步进。

### 关键坑

第一版用 int64 除法算斜率（`__aeabi_ldivmod` 库调用，100+ cycles），比 VDIV.F32（14 cycles）慢，
draw 从 13.60 → 14.05 ms（变慢）。改成"浮点除法一次 + 整数步进"后 13.50 ms。

### 结果

| | 前 | 后 |
|---|---|---|
| draw | 13.60 ms | **13.50 ms** |
| fps | 59.6 | **59.7** |
| 代码 | 578,876 B | **575,468 B** |
| 回归 T1–T5 | PASS | PASS |

收益仅 0.7% → **triangle setup 不是瓶颈**。
角色 10 万像素/2760 三角形 = 36 px/三角形，setup 摊销约 10 cycles/px，逐像素本身约 55 cycles/px。

### 下一步可选项

半分辨率渲染（像素÷4）、预乘 tint（退化成位拷贝）、合并 spine 附件减少三角形数。

---

## 2026-11-15 20:00 — 修复定点化引入的横向杂线

### 根因（两个）

1. **int32 溢出**：近水平边（高度<1px）斜率可达数万，`slope*65536` 溢出 int32 回绕，
   该行 x_right 变乱值 → 跨度横跨屏幕 → 横向杂线。
2. **修复中又引入 16 倍缩放错误**：`(yc - e_ylo) * step16` 少了 `>>4`
   （step 是每行增量，yc 是 4bit 单位）。回归立刻抓到：T1 缺 1781px、T3 画满 382320px。
   修正后回归通过但画面仍有杂线 → 说明定点逐行求交在极端斜率下仍不可靠。

### 处置

- 保留：定点包围盒（顶点移位取整）、纯定点绕序
- 回退：逐行边求交 → 浮点（此前从未出问题）

### 对比

| 版本 | draw | 回归 | 画面 |
|---|---|---|---|
| 纯浮点 | 13.60 | PASS | 干净 |
| 定点(int64除法) | 14.05 | PASS | 干净 |
| 定点(浮点斜率+整数步进) | 13.50 | PASS | **杂线** |
| 定点包围盒+浮点求交 | **13.47** | **PASS** | **干净** |

结论：逐行定点求交收益 0.7%，不值得其脆弱性，已回退。

---

## 2026-11-15 22:00 — 半分辨率渲染 API + 修复切换分辨率时的图层残留

### API

- `raster_upscale2x()`：脏矩形 2 倍最近邻放大
- `spine_play(..., divisor)`：divisor=2 渲染 400x240 后放大

### 实测

| 阶段 | 全分辨率 | 半分辨率 |
|---|---|---|
| clear | 1.55 | 0.39 |
| raster | 13.50 | 6.83 |
| present | 0.35 | 3.84 |
| 合计 | 15.4 | **11.1 ms（-28%）** |

raster 只降一半，因为 2760 三角形的 setup 与像素数无关。

### 踩的坑（3 个）

1. `d1 = d0 + dst_stride`（d0 是 uint32_t*，等于走 2 行）→ 用像素地址算
2. 缓存冲刷高度少乘 2
3. **切换分辨率时没清全尺寸缓冲**：先全分辨率后半分辨率 → 旧全分辨率画面残留在三块缓冲里，
   半分辨率只覆盖脏矩形 → "看到不该看到的图层 + 严重闪烁"。修复：每次播放前全清三块缓冲。

### 验证

半分辨率帧在角色包围盒外的非背景像素 = 0（无残影）。

### 待优化

present 3.84 ms 写 250 KB 仅 65 MB/s，瓶颈是 D-cache write-allocate。
可考虑 MPU 配 non-cacheable 或用 64 位宽存。

---

## 2026-11-16 00:30 — 半分辨率：未完成，已回退

### 现象（用户报告）

半分辨率播放时：严重闪烁、看到不该看到的图层、小图有残影（大图没有）、部分帧图层穿透。

### 定位到的确凿证据

半分辨率下只有第 0 块前台缓冲被写入：

- buf0 checksum 每次不同（有内容）
- buf1 / buf2 checksum **两次运行完全相同** = DC563E80（从未被写）

排除内存别名：写 0xC1A00000 = 0xA5A5A5A5 后 0xC0A00000 不受影响 → SDRAM ≥26MB 无别名。

### 已做的修复尝试（均未解决）

1. 三块低分辨率缓冲（每块前台对应一块 low）—— 无效
2. 播放前全清三块全尺寸缓冲 —— 无效

### 处置

回退到全分辨率播放（divisor=1）。当前板上状态：

```
t=6.0s avg 16.67 ms (60.0 fps) | clear 1.53 raster 13.50 present 0.35
包围盒外非背景像素: 0
```

半分辨率 API 保留但标记实验性、不可用。

### 教训

- 每轮补丁都在修"症状"，没有先建立"哪块缓冲被写"的可观测性 —— 应该第一步就打印三块缓冲的校验和
- 多次用 heredoc 打补丁导致 printf 字符串被破坏，浪费了若干轮

---

## 2026-11-16 02:00 — 半分辨率修复（真凶：draw_commands 用全局缓冲）

### 根因

`draw_commands()` 内部用全局 `s_surf` 作为渲染目标，而不是调用者的表面。
半分辨率路径新建了局部 `rs`（400x240）并清了它，但角色画进了全局全尺寸缓冲
（带着半分辨率变换 → 左上角大小不一的图形），低分辨率缓冲只有背景。
放大复制的是背景 → buf1/buf2 永远空白，buf0 只有"角色画错位置"的残留。

该 bug 同时影响全分辨率（所有帧都画进 buf0），只是不明显。

### 修复

`draw_commands(..., raster_surface_t *surf)` 显式传参；sheet 传 &s_surf，playback 传 &rs。

### 定位过程（关键）

1. 打印 draw_idx/dst/rect → 轮转正常
2. 打印放大后脏矩形校验和 → 写入确实发生
3. 三块缓冲最终校验和 → 只有 buf0 变化
4. 推断画错了目标 → 发现全局 s_surf

### 最终数据

| 阶段 | 全分辨率 | 半分辨率 |
|---|---|---|
| clear | 1.45 | 0.43 |
| raster | 13.47 | 6.90 |
| present | 0.35 | 3.80 |
| 合计 | 15.3 ms | **11.1 ms (-27%)** |
| fps | 60.3 | 64.8（60Hz 封顶） |

验证：三块缓冲非背景 48452/47036/47748，框外非背景全为 0。

---

## 2026-11-16 04:00 — 双角色 + 反复重载实验

### 结果

| 指标 | 全分辨率 | 半分辨率 |
|---|---|---|
| 加载 | 222 ms（纹理 55.8 / 读文件 7.5 / 解析 158.5） | 227 ms |
| 帧时间 | 37.09 ms | **25.45 ms** |
| 帧率 | **27.0 fps** | **39.3 fps** |
| clear/raster/present | 4.15 / 30.44 / 0.35 | 0.97 / 13.71 / 8.61 |
| 三轮一致性 | 27.0 x3 | 39.3 x3 |
| 删除后堆 | 405,288 恒定 | 405,288 恒定 |

### 发现并修复

1. **SkeletonData 泄漏**：`sd` 从未 delete，每轮 +350 KB（堆 716K→1.07M 且继续涨）。
   补 delete 后每轮回落到 405,288 B，稳定。
2. **分配器 O(n²)**：解析产生 7000+ 块，释放时从头扫前驱 → 解析 7239 ms。
   改双向链表 + 漫游指针后 **158.6 ms（46 倍）**。
3. **DWT 32 位回绕**：帧计时跨越 8.9 秒回绕点 → 算出 1929 fps 假数据。改逐帧累加。

### 结论

半分辨率对双角色提升 46%（27.0→39.3 fps）；加载 222 ms 可接受。
双角色 raster 是单角色的 2.25 倍（三角形数翻倍）。
半分辨率下 present 8.61 ms 成为第二大开销（D-cache 写分配，内存带宽受限）。

---

## 2026-11-16 05:00 — ARGB4444 支持

### 实现

- 转换器扩展为 `png_to_raw.py`，支持 `--fmt 1555|4444`（原名 png_to_argb1555.py 保留）
- `.raw` 文件头 format：1=1555, 2=4444
- 目标端：RawTexture 增加 fmt 字段，加载器接受两种，draw_commands 按格式分派
- 转换器对两种格式都支持 `--pma` 反预乘

### 验证

现有 1555 文件在新固件上无退化（load 222 ms / 37.10 ms/帧 / 27.0 fps）。

### 性能（栅格器基准）

1555：全屏常量色 11.20 Mpx/s，网格逐顶点 6.82
4444：全屏常量色 5.54 Mpx/s，网格逐顶点 3.46（约 1.97 倍慢，因每像素 3 次 ×17 展开）

### 待验证

需要把 4444 版 spineboy-pma.raw 拷到 SD 卡后跑双角色对比。

---

## 2026-11-16 06:00 — ARGB4444 实测对比

### 结果（双角色，各 3 轮）

| 场景 | ARGB1555 | ARGB4444 |
|---|---|---|
| 全分辨率 2 角色 | 37.10 ms / **27.0 fps** | 47.07 ms / **21.2 fps** |
| 半分辨率 2 角色 | 25.45 ms / **39.3 fps** | 27.34 ms / **36.6 fps** |
| 加载 | 222 ms | 223 ms |
| 三轮一致 | 27.0 x3 | 21.2 x3 |
| 删除后堆 | 405,288 B | 405,288 B |

4444 全分辨率慢 21%，半分辨率只慢 7%（present 占大头）。

### 测量缺陷（重要）

帧内分段计时不可信：全分辨率 draw 3.16 ms / 半分辨率 15.59 ms（像素数 4 倍却更快）。
怀疑与 VBR 等待和 volatile 重排有关。只有整帧时间可信，且与串口实际节奏吻合。
分段计时需要单独修。

### 画质

4444 让护目镜镜片呈半透明过渡；1555 当全不透明。按素材混用即可。

---

## 2026-11-16 07:00 — 用户素材 celestial-circus-pro 实测

### 素材

2 页 1024x1024 PNG（pma, scale 0.5）→ ARGB1555 各 2 MB，共 4 MB；67 regions / 7 动画：
eyeblink, eyeblink-long, stars, swing, wind-idle, wing-flap, wings-and-feet

### 双角色（swing + wing-flap，各 2 轮重载）

| | 全分辨率 | 半分辨率 |
|---|---|---|
| 加载 | 585 ms | 590 ms |
| 帧时间 | 87.37 ms | **46.05 ms** |
| 帧率 | **11.4 fps** | **21.7 fps** |
| 删除后堆 | 367,208 B 恒定 | 367,200 B 恒定 |

半分辨率提升 1.9 倍。角色当前拟合填满半屏（400x480/角色），实际游戏尺寸更小、开销线性下降。
加载 585 ms（4 MB @ 7 MB/s）。无泄漏。

### 备注

页内分段计时仍然不可信（全分辨率 draw 3.14 / 半分辨率 31.33），只有整帧时间可信。

---

## 2026-11-16 09:00 — 计时器修复

### 修好

1. DWT 32 位回绕（之前算出 1929 fps）→ 逐帧累加
2. 增加 HAL_GetTick 独立时钟交叉校验：frame 与 wall 差值 ≤0.01 ms
3. 相位和与帧时间差 >2 ms 时自动打印 [PHASE-SUM-INCONSISTENT]
4. 相位累加改 double，消除 uint32 溢出

### 验证

半分辨率：sum 46.06 = frame 46.06 = wall 46.06（自洽）
全分辨率：sum 12.78，frame 87.35，wall 87.35（自检报警）

### 结论

帧时间可信（双时钟一致）。全分辨率相位归因仍缺 74 ms；
证据表明是"相位读数错"而非"帧时间错"（92kpx/3.13ms = 30Mpx/s 不可能）。

### 下一步假设

全分辨率画进被 LTDC 扫描的全尺寸缓冲 → 总线竞争使耗时落到计时区间外。
验证：改成"画进独立缓冲再 memcpy"，看相位是否闭合。

---

## 2026-11-16 11:00 — 重力方向 API + 物理形变

### API

spine_set_gravity_dir(gx, gy) / spine_set_gravity(skel, gx, gy) → Skeleton::setGravityX/Y

### 两个根因（都是坑）

1. **Skeleton::update(dt) 从未调用**：物理步进 delta 来自 skeleton._time，而 _time 只在
   update(delta) 里推进 → delta 恒 0 → 物理一次都没跑。已补到 play/duo/gravity 三条路径。
2. **导出约束 gravity=0**：30 个物理约束的 gravity 都是 0，且 x/y 影响系数可能为 0，
   导致骨架重力向量无效。运行时统一 setGravity(1)/setX/Y/Rotate(1) 打开。

### 验证

静态姿势 + 只转重力：
t=0s dir=0 bone=(28.7,-860.1) rot=55.5
t=1s dir=72 bone=(42.2,-974.5) rot=66.6
t=2s dir=144 bone=(87.3,-816.1) rot=54.7
t=3s dir=216 bone=(72.5,-790.2) rot=65.4

两个重力方向画面差 22,814 像素（手臂/裙摆/绳索姿态明显不同）。

### 坑：重复注入约束会发散

在已有物理约束的骨骼上再注入一个 → 同一骨骼两个约束驱动 → 数值发散、画面散架。
教训：先查 constraints 数量，非 0 不要注入。

### 性能

单角色全分辨率 + 30 个物理约束：42.34 ms/帧（23.6 fps）。

---

## 2026-11-16 12:00 — 重力作用域澄清 + 世界级 API

### 问题

spine_set_gravity_dir 作用于世界还是单个对象？

### 事实

底层重力在 Skeleton 实例字段（_gravityX/_gravityY）→ **单个动画对象级**，没有全局重力。
头文件里之前的 spine_set_gravity_dir(gx,gy) 是悬空声明（未实现），已删除。

### 新增两层 API

- spine_set_gravity(skel, gx, gy) —— 单个对象（C++）
- spine_world_set_gravity(gx, gy) —— 世界级：存全局值 + 同步所有已注册骨架
- spine_register_skeleton / spine_unregister_skeleton —— 32 槽注册表，注册时继承当前世界重力
- spine_gravity_registry_count() —— 排查用

### 接线

- gravity 演示：注册骨架 + 世界里重力扫掠 → 骨骼运动数值与单对象版完全一致
- duo 路径：创建后注册、删除前注销

### 注意

注册表存裸指针，骨架销毁前必须注销，否则世界重力会写到已释放内存。

---

## 2026-11-16 14:00 — 计时器真正的根因：uint32 溢出

### 根因

相位累加器 uint32_t，240 帧循环下阈值 = 2^32/480000/240 = 37.28 ms/帧。
- 半分辨率 draw 31.5 < 37.28 → 不溢出 → 自洽（误导了我好几轮）
- 全分辨率 draw 82.5 > 37.28 → 回绕显示成 3.13

帧总时间用 uint64 所以一直是对的 → 出现"帧对、分段错、差 74ms"。
74.6 ms 正是 2^32 取模吃掉的量。

### 修复

相位累加器全部 uint32 → uint64_t，打印转 double。

### 修复后真实数据（circus 双角色 240 帧）

| 阶段 | 全分辨率 | 半分辨率 |
|---|---|---|
| anim | 1.01 | 1.00 |
| build | 4.13 | 4.25 |
| clear | 4.23 | 1.02 |
| **draw** | **82.51** | **31.52** |
| present | 0.35 | 8.72 |
| sum | 92.23 | 46.52 |
| frame/wall | 92.23/92.22 | 46.52/46.52 |

### 结论

光栅占 89%/68%，是绝对瓶颈。present 只占 19%，第二优先。
光栅速率 1.1 Mpx/s（全）/0.73（半），远低于基准 6.8 → 4 MB 图集撑爆 16 KB D-Cache。
优化优先级改为：先做纹理局部性（降图集尺寸/分页常驻/swizzle），再优化 present。

---

## 2026-11-16 15:00 — 图集缩放实测（4 MB → 1 MB）

导出 scale 0.5→0.25，2 页 1024x1024 → 1 页 1024x512。

| 指标 | 4 MB | 1 MB | 变化 |
|---|---|---|---|
| 加载 | 587 ms | 262 ms | -55% |
| 全分辨率双角色 | 92.23 ms / 10.8 fps | 57.90 ms / 17.3 fps | **+60%** |
| 半分辨率双角色 | 46.52 ms / 21.5 fps | 36.30 ms / 27.5 fps | +28% |
| draw 全 | 82.51 | 48.40 | -41% |
| draw 半 | 31.52 | 21.93 | -30% |
| present 半 | 8.72 | 8.30 | 持平 |

光栅速率：4MB 1.1 Mpx/s → 1MB 1.9 Mpx/s（spineboy 512KB 对照 7.4）。

结论：纹理内存是光栅一阶因素，零代码改动 +60%。
且图集越小 present 占比越大（23%），present 优化优先级随之上升。

---

## 2026-11-16 17:00 — present 优化（8.30 → 5.45 ms）

### 先量上限

600 KB 填充：32 位 144 MB/s，64 位 170 MB/s（WT），clean 0.28 ms。
**MPU 属性对 32 位存储完全无影响** → "write-allocate 翻倍流量"假设错误。

### 改动

raster_upscale2x 重写：
- 按目标行顺序写（单流，原来是 2y/2y+1 交替两条流）
- 64 位宽存（2 源像素 → 4 输出像素）
- 8 字节对齐前缀 + 奇数尾像素

同时：MPU 写穿（基准 +12%，实测 0）、去掉冗余冲刷（实测 0）。

### 结果

| 指标 | 前 | 后 |
|---|---|---|
| present 半 | 8.30 ms | **5.45 ms** (-34%) |
| 半分辨率帧 | 36.30 | **33.53** |
| 半分辨率 fps | 27.5 | **29.8** (+8.4%) |
| 全分辨率帧 | 57.90 | 57.95（持平） |

### 现状

present 流量 = 读 192KB + 写 600KB = 792KB / 5.45ms = 145 MB/s，上限 170 → 85% 饱和。
后续只能靠减少流量：把 2x 放大合并进光栅器（省 384 KB），预计 -3 ms。
风险：三角形内分散写的行命中率不如顺序放大，需实测。

---

## 2026-11-16 18:30 — 修复半分辨率竖向条纹（64 位字节序）

### 原因

重写 raster_upscale2x 时把 64 位打包的字节序写反：
packed = (a<<48)|(a<<32)|(b<<16)|b  → 输出 [b,b,a,a]（每对源像素颠倒）
正确应为 a | (a<<16) | (b<<32) | (b<<48) → [a,a,b,b]

小端机低位对应低地址，写反后细节区域出现 2 像素周期错位 → 竖向条纹模糊。
全分辨率不走放大路径，所以不受影响。

### 验证

- 扫描线游程长度：全部为 2，0% 奇数长度
- 偶数列与右邻列相同比例：100.0%

### 最终数据（1 MB 图集）

全分辨率双角色 57.95 ms / 17.3 fps（draw 48.49）
半分辨率双角色 33.54 ms / 29.8 fps（draw 22.01 + present 5.47）

---

## 2026-11-16 20:00 — API 规范化（资产/实例/每帧绘制）

### 新增文件

- User/spine_api.h —— C 接口（资产、实例、绘制、世界重力）
- User/spine_api.cpp —— 实现

### 分层调整

把 RawTexture / load_raw_texture / RawTextureLoader / blend_of / arena 从 spine_test.cpp
移到 spine_platform.cpp/.h（平台层），测试文件只留基准与演示。

### 两个 bug

1. **heap_init 非幂等**：SpineMcuExtension 惰性构造时构造函数调 heap_init() 重置整个堆，
   导致先分配的 asset 结构体被后分配的对象覆盖 → 虚表损坏 → HardFault(PC=0x28)。
   修复：heap_init 幂等。
2. **半分辨率变换未除 divisor**：实例 position/scale 是屏幕像素，画进 1/divisor 的缓冲
   需乘 1/divisor，否则位置尺寸 ×2 且脏矩形错误。修复：新增 g_d.inv_divisor。

### 验证

[API] asset loaded: 7 animations | 1 textures
[API] bounds=(-755,-1809)-(577,556) scale=0.093
[API] 300 frames | 19.71 ms/frame (50.7 fps) | instances=2 queue=2
[API] after free: instances=0
[API] RESULT PASS

画面：左右两个角色（左 swing 原色、右 wing-flap 带冷色 tint），位置正确。

---

## 2026-11-16 22:00 — 可移植封装（平台抽象层）

### 新增

- User/plat/plat_cfg.h —— 屏幕/缓冲/对齐/能力开关
- User/plat/plat.h —— 六组共 17 个接口
- User/plat/plat_stm32h7.c —— H743 实现（内存池/文件系统/LTDC/缓存/时间/日志/MPU）

### 改造

| 文件 | 改动 |
|---|---|
| spine_platform.cpp | 写死地址 -> plat_mem_pools；FatFs -> plat_file_* |
| spine_api.cpp | LTDC 寄存器 -> plat_fb_present；cache 判断 -> plat_fb_need_cache_clean |
| raster2d.cpp | SCB_CleanInvalidateDCache -> plat_cache_clean |
| spine_test.cpp | fb_mpu_set -> plat_fb_set_cache_mode |

### 接线时踩的坑

_readFile 只替换了打开部分，读取部分仍用未初始化的 FIL -> HardFault（PC 在异常处理区）。
补全后才通过。**教训：分步替换一个函数时必须整函数替换，不能只换一半。**

### 验证（封装前后一致）

| 测试 | 封装前 | 封装后 |
|---|---|---|
| 全分辨率双角色 | 57.85 / 17.3 fps | 57.89 / 17.3 fps |
| 半分辨率双角色 | 33.46 / 29.9 fps | 33.65 / 29.7 fps |
| API 双实例 | 19.71 / 50.7 fps | 19.80 / 50.5 fps |

驱动/光栅/TGX 自检全 PASS，API RESULT PASS。

---

## 2026-11-16 23:30 — RTOS 适配（宏开关）

### plat_cfg.h 新增

PLAT_USE_RTOS       0 = 裸机 / 1 = RTOS
PLAT_ENABLE_MEM_LOCK 1 = 分配器加递归互斥

### plat.h 新增

- plat_init()（RTOS 下建信号量、打开 LTDC 重装中断）
- plat_fb_wait_ready()
- plat_os_* 钩子：sem_create/take/give_isr、delay_ms、tick_ms、mem_lock
- 裸机时全部为空宏，库代码无条件调用即可

### plat_stm32h7.c

- 等 vsync：裸机轮询 / RTOS 等信号量（让出 CPU）
- delay / now_ms：按宏切换 HAL 或 OS
- RTOS 下定义 LTDC_IRQHandler（RRIF -> give semaphore）
- 分配器：heap_alloc/free 内部加锁（裸机为空）

### 新增模板

User/plat/plat_os_freertos.c.template —— FreeRTOS 适配，改名即用

### 验证

裸机模式真机验证：duo 57.87 / 33.57 ms，API 加载正常，与封装前一模一样。
RTOS 模式未编译验证（工程里还没有 FreeRTOS），需接入后实测。
