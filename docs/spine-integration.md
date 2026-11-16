# Spine 4.3 运行时代码集成（Phase 2）

## 已完成

| 步骤 | 状态 |
|---|---|
| spine-cpp 4.3 源码进入工程（`Middlewares/SPINE`，88 个 .cpp + 113 个头文件） | ✅ 全部编译通过，0 error |
| 平台层 `User/spine_platform.cpp`：SDRAM first-fit 分配器 + `getDefaultExtension()` + FatFs `_readFile` | ✅ |
| 集成层 `User/spine_test.cpp`：Atlas / SkeletonBinary / AnimationState / SkeletonRenderer → `raster_mesh` | ✅ 编译链接通过 |
| 素材管线：PNG → ARGB1555 raw（`DSH/middleware/png_to_argb1555.py`） | ✅ spineboy 已转换 |
| 板级验证 | ✅ spineboy 正确渲染，20.19 ms/帧（49.5 fps） |

代码量：581 KB（Flash 2 MB 余量充足）；AXI SRAM 占用不变（顶点缓冲放在 SDRAM arena）。

## 关键设计

* **内存**：SDRAM 划出 8 MB 作为 spine 堆（`0xC0200000`），16 MB 作为纹理/资源 arena（`0xC0A00000`），
  完全绕开 C 库堆（`Heap_Size` 默认 0）。
* **渲染**：spine-cpp 4.3 自带 `SkeletonRenderer`，直接产出 `RenderCommand{positions, uvs, colors, indices, blendMode, texture}`，
  正好是自写光栅器 `raster_mesh()` 的输入；`SkeletonClipping` 已在渲染器内部完成裁剪。
* **颜色**：`RenderCommand.colors` 是 ARGB8888 且每条命令内恒定 → 走光栅器最快的 COLMODE 0 路径。
* **纹理**：AtlasPage.format 忽略，统一由 `RawTextureLoader` 从 `/spine/<page>.raw` 读 ARGB1555。

## 踩到的两个坑

1. **`__stdout` 重复定义**：spine 的 `printf` 把 C 库 `stdio_streams.o` 拉进链接，与 `usart.c` 里手写的
   `FILE __stdout` 冲突（L6200E）；反过来，若去掉自己那份，C 库版本又引入 `_sys_open` 与 `__use_no_semihosting` 冲突（L6915E）。
   最终方案：保留自己的 `__stdout`，并把 `Skeleton::printUpdateCache()` 里的 `printf` 编译掉（该函数仅调试用）。
2. **静态初始化早于 SDRAM 初始化**：`SpineMcuExtension` 曾是全局对象，构造时写 SDRAM（尚未初始化）→ 上电无任何输出。
   改成函数内静态、首次调用才构造（`getDefaultExtension()` 里 placement new）。

## 素材部署

把 `spine_assets/` 下的三个文件拷到 SD 卡：

```
/spine/spineboy-pro.skel     (65 KB)
/spine/spineboy-pma.atlas    (1.6 KB)
/spine/spineboy-pma.raw      (512 KB, ARGB1555)
```

## 调试过程中定位的 4 个 bug

| # | 现象 | 根因 | 修复 |
|---|---|---|---|
| 1 | 上电无任何串口输出 | `SpineMcuExtension` 是全局对象，构造时写 SDRAM（SDRAM 在 main 才初始化） | 改惰性构造（首个调用时 placement new） |
| 2 | `L6920E: __stdout multiply defined` / `L6915E: _sys_open` | spine 的 printf 把 C 库 stdio_streams.o 拉进来 | 保留自己的 `__stdout`，编译掉 `Skeleton::printUpdateCache()` 的 printf |
| 3 | 角色上下颠倒 | spineboy-pro 的世界 Y 是向下的（包围盒 -678..8） | 改为直通映射 `y*scale+oy`，offset 由测得包围盒推出 |
| 4 | **颜色全错（绿头发/紫枪），且改解码代码完全无效果** | `RAW_COPY` 快路径只对 RGB565 源成立，却把 ARGB1555 的原始 texel **直接写进 RGB565 帧缓冲** | `dispatch_color` 里加 `FMT == 0` 守卫 |

> 第 4 个最隐蔽：因为走的是 RAW_COPY 分支，改 ARGB1555 的解包代码完全无效，容易误判成"固件没更新"。

## 性能

| 指标 | 数值 |
|---|---|
| spineboy-pro（67 骨骼 / 52 槽位 / 11 动画） | **20.19 ms/帧 = 49.5 fps** |
| 渲染命令 | 30 条，8280 顶点 |
| 纹理 | 1024×256 ARGB1555（512 KB，SDRAM） |
| spine 堆 | 417 KB（峰值 429 KB，0 次失败） |
| 代码量 | 582 KB / 2 MB Flash |

## 待办

* 板级跑通后：测量真实动画帧率、优化变换（目前每帧 memcpy 命令顶点）
* 支持 `darkColors`（双色 tint）——当前渲染器忽略
* 支持多页图集（当前 loader 已按 page 名映射，多页天然支持）

## 动画验证（spineboy-pro 示例）

示例骨架内置 **11 个动画**，无需另外下载：

| # | 名称 | # | 名称 |
|---|---|---|---|
| 0 | aim | 6 | portal |
| 1 | death | 7 | run |
| 2 | hoverboard | 8 | run-to-idle |
| 3 | idle | 9 | shoot |
| 4 | idle-turn | 10 | walk |
| 5 | jump | | |

### 动画总览（单帧拼接）

`spine_anim_sheet()` 把每个动画在 t=0.45s 的姿态渲染到一个 4×3 网格（每格 200×160），
一次 dump 就能看到全部 clip：

* 11 格渲染总耗时 **94.8 ms**（平均 8.6 ms/角色，因为格子只有 1/12 屏面积）
* 其中 `jump` / `portal` 在 t=0.45s 时角色恰好移出格内或只剩特效，属时间点选择问题，非渲染错误

### 运动校验（证明动画在推进，而非静态姿势）

同一 clip（run）在 t=0.45 与 t=0.75 各渲染一次并比较单元格校验和：

```
[SPN] motion check (run): t0=C3BBFF7A t1=F72A5703 MOVING
```

校验和不同 → `AnimationState` 的时间推进、`apply()`、`updateWorldTransform(Physics_Update)` 都在正常工作。

## 实时播放（walk）

`spine_play(skel, atlas, anim, fps, seconds)`：

* **双缓冲**：前台缓冲 0xC0000000、后台缓冲 0xC1A00000，每帧渲染完后台后写
  `LTDC_Layer1->CFBAR` + `LTDC->SRCR = VBR`，在垂直回扫时切换 → **无撕裂**；
* 固定步长 `dt = 1/fps`，渲染耗时不足一帧时用 `delay_ms` 补齐；
* 每满 1 秒打印 avg/min/max 帧时间。

### 实测（walk @ 30 fps，20 秒）

```
[SPN] realtime playback: walk @ 30 fps for 20 s
[SPN] playback fit: scale=0.641 ox=387 oy=455
[SPN] t=1.0s  avg 33.83 ms  min 20.64  max 70.59  (29.6 fps)
[SPN] t=2.0s  avg 32.57 ms  min 20.14  max 24.42  (30.7 fps)
...
[SPN] t=11.0s avg 32.48 ms  min 20.47  max 24.37  (30.8 fps)
```

| 指标 | 数值 |
|---|---|
| 稳态帧率 | **30.8 fps**（目标 30 fps） |
| 纯渲染耗时 | **20.1 – 24.4 ms** |
| 每帧余量 | ~9–13 ms（delay 补齐到 33 ms） |

### 运动确认

播放结束后两块缓冲各留有**不同的一帧**，逐像素比较：

```
两帧不同像素数: 42535 / 384000 (11.1%)
```

→ 动画确实在推进（不是静止姿势）。

### 帧率上限分析

角色占屏约 256×420，覆盖率约 70% ⇒ ~75k 像素/帧；当前光栅器 ≈5–6 Mpx/s ⇒ 13–15 ms，
加上 30 条命令的顶点变换与 setup，实测 20–24 ms。

* **30 fps（33 ms 预算）：有余量** ✅
* **60 fps（16.6 ms 预算）：当前达不到** ❌，需要
  （a）缩小角色/降低分辨率，或（b）更快的混合路径（预乘 tint / 565 原生色调），
  或（c）减少每帧顶点变换开销。

## 性能优化（顶点变换 + 混合路径）

先用计时把一帧拆开，再针对性优化：

| 阶段 | 优化前 | 优化后 | 手段 |
|---|---|---|---|
| 清屏 | ~5.0 ms（全屏 384k px） | **1.75 ms** | 只清角色包围盒（占屏 32%） |
| 绘制 | ~19.0 ms | **14.3 ms** | ARGB1555 565 原生快路径 |
| **单帧合计** | **20–24 ms** | **16.85 ms** | |
| 帧率 | 30 fps（有余量） | **59.4 fps** | |

### 1) 局部清屏

角色包围盒 (261,16)-(538,464) 只占屏幕 32%，全屏清屏是纯浪费。
播放开始时对两块缓冲各做一次全清，之后每帧只清 bbox。

### 2) ARGB1555 565 原生快路径

`raster2d.cpp` 内层为 `FMT==1 && COLMODE==0 && BLEND==0` 增加两条路径：

* **白色色调 + 不透明**（Spine 最常见）：1555 → 565 纯位重组，不做任何 8bit 往返
  ```
  out = ((texel >> 10) & 0x1F) << 11 | (((texel >> 5) & 0x1F) << 1) << 5 | (texel & 0x1F)
  ```
* **有色调**：在 5-5-5 空间乘色调（预先把 tint 转成 0..32 的乘数），再 `lerp565` 混合

选择用**循环不变谓词**（`white_tint`、`opacity`），每像素分支完全可预测。

### 3) 顶点变换：实测不是瓶颈

每帧 8280 个顶点，变换开销：

```
8280 × (2 mul + 2 add + 2 mul + store) ≈ 60k cycles ≈ 0.12 ms
```

占 16.85 ms 的 **0.7%**，优化它没有意义。真正的成本在**逐像素光栅化**：
2760 个小三角形（平均 25 像素/三角形），每三角形 ~400 cycles 的 setup 约占 2.3 ms，
其余 ~12 ms 是逐像素开销。

### 优化后的实测

```
[SPN] realtime playback: walk @ 60 fps for 15 s
[SPN] dirty rect: (261,16)-(538,464) = 32% of screen
[SPN] t=2.0s  avg 16.84 ms  min 14.69  max 19.32  (59.4 fps)  clear 1.74 ms / draw 14.23 ms
[SPN] t=3.0s  avg 16.84 ms  min 14.69  max 19.32  (59.4 fps)  clear 1.74 ms / draw 14.23 ms
```

**60 fps 达成**（59.4 fps 稳定，余量 ~0.2 ms —— 已经很紧）。

## 闪烁 / 残影问题分析与修复

### 现象

播放 walk 时：角色摆动的手臂/枪尖处有**残影**，且该区域**闪烁**。

### 根因（两个叠加的错误）

**错误 1：脏矩形只在开头算了一次**

原来的脏矩形来自 **setup pose 的包围盒**，整个播放过程复用：

```cpp
int bx0 = (int)(wminx * scale + ox) - 4;   // 只算一次
...
clear_rect(&s_surf, bx0, by0, bx1, by1, BG);   // 每帧都清这块固定区域
```

walk 动画中手臂会甩出这个范围，超出的旧像素永远不被清 → **残影**。

**错误 2：双缓冲的 2 帧延迟没算进去**

一开始我改成"当前帧 + 上一帧包围盒的并集"，仍然有问题。原因是：

> 双缓冲下，缓冲区 X 里存的是 **两帧前**（N-2）的画面。
> 在第 N 帧往 X 里画时，必须清掉 X 里 N-2 帧的残留，
> 而"N-1 帧的包围盒"和 X 的内容无关。

所以正确做法是**按缓冲分别记录上一帧包围盒**：

```cpp
int pbx[2], pby[2], pbX[2], pbY[2];   // 每块缓冲一份
int parity = 0;                        // 当前画的是哪块

clear_rect(union(current_bbox, pb[parity]));
draw();
pb[parity] = current_bbox;
parity ^= 1;
```

### 闪烁的成因

残影区域在两块缓冲里内容不同：
* 缓冲 A：还留着**上一轮**的手臂像素
* 缓冲 B：已被清成背景

LTDC 每帧交替扫描 A/B，这个区域就以 **30 Hz**（60fps 的一半）在"手臂残影"和"背景"之间跳变 —— 这就是肉眼看到的**闪烁**。

所以残影和闪烁是**同一个 bug 的两种表现**。

### 量化验证

暂停时同时 dump 两块缓冲，统计**角色包围盒之外**的差异像素：

| 版本 | 框外差异像素 |
|---|---|
| 固定脏矩形（setup pose） | 明显残影（手臂区域成片） |
| 当前帧 + 上一帧并集 | **740 px**（x 542–566, y 330–381，正是手臂/枪） |
| **按缓冲分别记录** | **0 px** ✅ |

### 修复后的性能

| 指标 | 数值 |
|---|---|
| 帧率 | **59.8 fps**（60 目标） |
| 清屏 | 2.2 ms（脏矩形变大，仍只占屏 ~35%） |
| 绘制 | 13.6 ms |
| 单帧 | 16.7 ms |

### 仍未解决的隐患

帧时间 16.0 ms vs 60fps 预算 16.67 ms —— **余量只有 0.6 ms**。
若某帧偶然超时，`CFBAR` 的 VBR 请求会延后一个垂直回扫，表现为**重复一帧**（judder，不是闪烁）。
要稳定 60fps 需要再压缩 2–3 ms，或降到 50fps 留余量。

## 闪烁的真正根因：往"还在显示"的缓冲里画（已改为三缓冲）

### 症状

修复残影后，用户仍报告：**纵向的黑色区域在人物区域上不断闪烁**。

### 分析

"纵向黑色区域"= 脏矩形（角色包围盒是竖直长条，x 261–538 / y 16–464），
"黑色" = 清屏色 0x0861。

双缓冲的时序是这样的：

```
清屏 -> 绘制 -> 请求 VBR 切换 -> 立刻开始往"旧前台"画
                                  ^^^^^^^^^^^^^^^^^^^^
                                  但旧前台要等到下一个垂直回扫才被换下！
```

`LTDC->SRCR = VBR` 只是**请求**在下一个 vblank 切换。在切换真正发生之前，
旧前台**仍在被扫描显示**，而我们已经在往里清屏和绘制了 —— 观众直接看到
清屏矩形（竖条）盖在角色上 → **纵向黑色区域闪烁**。

用数字说明严重程度：绘制耗时 13.6 ms / 帧周期 16.7 ms ⇒ **81% 的时间都在往显示中的缓冲里写**。

### 修复：三缓冲

```
3 块缓冲；画的那块永远既不是"正在显示"的，也不是"待切换"的
```

```cpp
uint16_t *bufs[3] = { FB0, FB1, FB2 };
int draw_idx = 1;

// 每帧：
draw_into(bufs[draw_idx]);
flush(bufs[draw_idx]);
while (LTDC->SRCR & LTDC_SRCR_VBR) {}   // 等上一次切换完成
LTDC_Layer1->CFBAR = bufs[draw_idx];
LTDC->SRCR = LTDC_SRCR_VBR;
draw_idx = (draw_idx + 1) % 3;          // 轮到下一块（不显示、不待切换）
```

每块缓冲各自维护脏矩形（三缓冲 => 3 帧延迟），避免残影。

### 验证

暂停时同时 dump 三块缓冲，统计角色区域内的非背景像素占比（完整帧应约 29%）：

| 缓冲 | 非背景占比 |
|---|---|
| tb0 | 29.4% |
| tb1 | 29.2% |
| tb2 | 28.8% |

**三块全部是完整帧**，没有任何一块处于"已清屏、未绘制"的半成品状态。

### 性能

| 指标 | 数值 |
|---|---|
| 帧率 | **59.6 fps** |
| 清屏 | 1.6 ms |
| 绘制 | 13.6 ms |
| 单帧工作 | ~15.2 ms（预算 16.67 ms，余量 ~1.4 ms） |

## 三角形定点化（setup 优化）

### 做了什么

把 `raster_tri()` 的三角形 setup 从浮点改为定点：

| 项 | 之前 | 现在 |
|---|---|---|
| 包围盒 | 浮点 min/max + `floorf/ceilf` | 直接用 4bit 定点顶点移位取整 |
| 绕序判断 | 定点 area + 浮点坐标同步交换 | 纯定点，不再维护浮点副本 |
| 边 x(y) | 每行 `ex_int + fy*slope`（浮点乘加） | 16.16 定点增量，每行一次整数加法 |
| 行跨度 | `ceilf/floorf` | 整数移位 `(xa16+0x7FFF)>>16` |

### 踩到的坑：int64 除法比浮点除法慢

第一版用 `int64` 算边斜率：

```cpp
e_step16 = (int32_t)((((int64_t)dx) << 16) / dy);   // 变成 __aeabi_ldivmod 库调用
```

Cortex-M7 上 **int64 除法是库函数（100+ cycles）**，而 `VDIV.F32` 只要 14 cycles。
实测 draw 从 13.60 → **14.05 ms（变慢）**。

改为"**浮点除法求斜率一次 + 16.16 定点增量步进**"后：

```cpp
float slope = (float)dx / (float)dy;          // VDIV 14 cycles，每三角形一次
e_step16[e] = lrintf(slope * 65536.0f);
e_x16[e]    = lrintf((xa + (yc0 - ya) * slope) * 4096.0f);
```

### 结果

| 指标 | 浮点版本 | 定点版本 |
|---|---|---|
| draw | 13.60 ms | **13.50 ms** |
| clear | 1.6 ms | 1.6 ms |
| 帧率 | 59.6 fps | **59.7 fps** |
| 代码 | 578,876 B | **575,468 B**（−3.4 KB） |
| 回归 T1–T5 | PASS | **PASS** |

**收益只有 0.7%，说明三角形 setup 不是瓶颈。**

### 为什么 setup 不是瓶颈

角色约 10 万像素 / 2760 个三角形 ≈ 36 像素/三角形，setup 摊销后约 10 cycles/px，
而逐像素路径本身约 55 cycles/px。想再快只能：

1. **减少像素数**（半分辨率渲染，像素 ÷4）
2. **更快的像素路径**（预乘 tint，把色调烘进纹理，退化成位拷贝）
3. **减少三角形数**（合并 spine 附件）

顺带记录一个反直觉的实测：栅格器基准里"网格 768 三角形"（5.5 Mpx/s）远慢于"全屏四边形"（27.8 Mpx/s），
但那**不是三角形开销**，而是因为网格基准用的是逐顶点色调（COLMODE 2），四边形用的是 RAW_COPY 常量色。

## 定点化的回归：横向杂线（已修复）

### 症状

人物部件附近出现**横向杂线条**，跟随部件运动。放大后看清：同一 y 行上、从头部向右伸出的
若干**1 像素高的肤色短横线**，每条来自不同三角形。

### 根因 1：int32 溢出（近水平边）

```cpp
float slope = (float)dx / (float)dy;     // dy 可能只有 1 个 4bit 单位（0.06 px）
e_step16 = lrintf(slope * 65536.0f);     // slope 可达数万 -> 溢出 int32
```

近水平边（高度不足 1 像素）的斜率可达几万，`slope * 65536` 超出 int32 回绕，
导致该行的 `x_right` 变成乱值 → 跨度横跨屏幕 → 横向长条。

### 根因 2：修复时又引入的 16 倍缩放错误

改成"从边自己的起始行起算"后，我用了：

```cpp
e_x16 = e_xstart16 + (yc - e_ylo) * e_step16;   // 错！
```

`step16` 是**每行**增量，而 `(yc - e_ylo)` 是 4bit 单位（1 行 = 16 单位），
少除以 16 → 增量放大 16 倍。回归测试立刻抓到：T1 覆盖缺失 1781 px、T3 画满 382320 px。

修正为 `((yc - e_ylo) * step16) >> 4` 后回归通过，但**画面仍有杂线**——
说明近水平边的精度问题不止一处。

### 最终处置：保留安全部分，逐行求交退回浮点

| 部分 | 处置 | 理由 |
|---|---|---|
| 包围盒（定点顶点移位取整） | ✅ 保留 | 无风险，省掉浮点 min/max + 转换 |
| 绕序判断（纯定点） | ✅ 保留 | 无风险，省掉浮点副本交换 |
| **逐行边求交** | ↩️ **退回浮点** | 定点增量在极端斜率下脆弱；浮点版本从未出问题，且性能相同 |

### 对比

| 版本 | draw | 回归 | 画面 |
|---|---|---|---|
| 纯浮点 | 13.60 ms | PASS | 干净 |
| 定点（int64 除法） | 14.05 ms | PASS | 干净 |
| 定点（浮点斜率+整数步进） | 13.50 ms | PASS | **横向杂线** |
| **定点包围盒 + 浮点求交** | **13.47 ms** | **PASS** | **干净** ✅ |

结论：**逐行定点求交的收益（0.1 ms，0.7%）不值得它的脆弱性**，已回退。
保留的定点包围盒/绕序部分既安全又保留了代码体积收益。

## 半分辨率渲染 API

### 接口

```c
/* raster2d.h —— 2 倍最近邻放大（只放大脏矩形） */
void raster_upscale2x(const uint16_t *src, int src_stride,
                      uint16_t *dst, int dst_stride,
                      int sx0, int sy0, int sx1, int sy1);

/* spine_test.h —— divisor: 1=全分辨率, 2=半分辨率 */
uint8_t spine_play(const char *skel, const char *atlas, const char *anim,
                   int fps, int seconds, int divisor);
```

`divisor=2` 时渲染到 400×240（1/4 像素），再把**脏矩形**2 倍放大到 800×480 的三缓冲之一。
只放大脏矩形是关键——全屏放大（384k 输出像素）会把省下来的时间全部吃掉。

### 实测（walk，60fps 目标）

| 阶段 | 全分辨率 | 半分辨率 |
|---|---|---|
| clear | 1.55 ms | **0.39 ms** |
| raster | 13.50 ms | **6.83 ms** |
| present（放大） | 0.35 ms | **3.84 ms** |
| **合计工作量** | **15.4 ms** | **11.1 ms（−28%）** |
| 帧率 | 60.0 fps（受 60Hz 限制） | 60.0 fps（实际 64.8 fps 上限） |

`raster` 只降到 1/2 而非 1/4，是因为 2760 个三角形的 setup 与像素数无关。

### 踩的坑

1. **放大函数指针算术错误**：`d1 = d0 + dst_stride` 中 `d0` 是 `uint32_t*`，
   加 800 等于走了 2 行（应为 `dst + (2y+1)*dst_stride`）。
2. **缓存冲刷范围少算一半**：高度要 ×2（放大后行数翻倍）。
3. **切换分辨率时没清全尺寸缓冲**（最严重）：先跑全分辨率再跑半分辨率时，
   三块全尺寸缓冲仍是旧的全分辨率画面；半分辨率只把脏矩形覆盖上去，
   其余区域就露出**旧图层**——表现正是"闪烁极其严重 + 看到不该看到的图层 + 半分辨率残影"。
   修复：每次播放开始前把三块全尺寸缓冲 + 低分辨率缓冲全部清一次。

### 当前瓶颈

`present` 3.84 ms 写约 250 KB，仅 65 MB/s——这是 **D-cache 写分配（write-allocate）**
导致的（每次写未命中要先取整条 cache line，流量≈2×）。

优化方向：把帧缓冲所在 MPU 区域配成 non-cacheable / write-through-no-allocate，
或用 64 位宽存储填充整行。预计可把 present 降到 1.5–2 ms，总工作量降到 ~9 ms。

## 半分辨率渲染（已修复并验证）

### API

```c
/* raster2d.h */
void raster_upscale2x(const uint16_t *src, int src_stride,
                      uint16_t *dst, int dst_stride,
                      int sx0, int sy0, int sx1, int sy1);

/* spine_test.h —— divisor: 1=全分辨率, 2=半分辨率 */
uint8_t spine_play(const char *skel, const char *atlas, const char *anim,
                   int fps, int seconds, int divisor);
```

`divisor=2` 渲染到 400×240，再把**脏矩形**放大到 800×480 的三缓冲之一。
三块低分辨率缓冲与三块前台缓冲一一对应（每块有自己的历史，避免跨帧污染）。

### 根因（找了很久的那个 bug）

`draw_commands()` 里用的是**全局 `s_surf`**，而不是调用者传进来的目标：

```cpp
static void draw_commands(spine::RenderCommand *cmd, float scale, float ox, float oy)
{
    ...
    raster_mesh(&s_surf, ...);      // ← 永远是全局缓冲
}
```

半分辨率路径新建了局部 `rs`（400×240）并清了它，但角色被画进了全局的全尺寸缓冲
（还带着半分辨率的变换 → 挤在左上角），低分辨率缓冲里只有清屏色。
放大时把这堆背景复制进缓冲 1、2 —— 于是：

| 现象 | 解释 |
|---|---|
| 只有 buf0 有画面 | 角色一直画在全局缓冲（=buf0） |
| buf1/buf2 校验和恒定 | 它们只被放大了"背景" |
| 严重闪烁 | 三块内容不一致，LTDC 轮流显示 |
| 图层穿透/缺失 | 脏矩形外的部分从未被正确填充 |

**这个 bug 同时也影响全分辨率路径**（所有帧都画进 buf0），只是全分辨率下 buf0 每帧都更新，
不容易看出来。

### 定位方法（值得记下来）

1. 打印 `draw_idx` / `dst` / 脏矩形 → 轮转正常、地址正确
2. 打印**放大后脏矩形的校验和** → 说明写入确实发生了
3. 对比三块缓冲最终校验和 → 只有 buf0 变化
4. 结合"角色出现在左上角且是半分辨率变换"→ 推断出画进了错误的目标
5. 确认 `draw_commands` 用的是全局 `s_surf` → 修复：把它改成显式参数

### 最终实测

| 阶段 | 全分辨率 | 半分辨率 |
|---|---|---|
| clear | 1.45 ms | **0.43 ms** |
| raster | 13.47 ms | **6.90 ms** |
| present（放大） | 0.35 ms | **3.80 ms** |
| **合计** | **15.3 ms** | **11.1 ms（−27%）** |
| 帧率 | 60.3 fps | 64.8 fps（60Hz 封顶） |

验证：三块缓冲非背景像素 48,452 / 47,036 / 47,748，**角色框外非背景像素全部为 0**。

## 双角色 + 反复重载实验

`spine_play_duo(skel, atlas, animA, animB, fps, seconds, divisor, iterations)`：
两个独立 skeleton 播不同动画，**每轮都重新从文件加载**，并打印加载分解、帧率、堆统计。

### 结果（每轮 4 秒，各 3 轮）

| 指标 | 全分辨率 | 半分辨率 |
|---|---|---|
| 加载 | **222 ms**（纹理 55.8 + 读文件 7.5 + 解析 158.5） | 227 ms |
| 帧时间 | 37.09 ms | **25.45 ms** |
| **帧率** | **27.0 fps** | **39.3 fps** |
| clear | 4.15 ms | 0.97 ms |
| raster | 30.44 ms | 13.71 ms |
| present（放大） | 0.35 ms | 8.61 ms |
| 三轮一致 | 27.0 / 27.0 / 27.0 | 39.3 / 39.3 / 39.3 |
| 删除后堆占用 | 405,288 B 恒定 | 405,288 B 恒定 |

**半分辨率对双角色提升 46%（27.0 → 39.3 fps）。**

### 实验发现并修复的两个 bug

#### 1) SkeletonData 内存泄漏（每轮 350 KB）

```cpp
spine::SkeletonData *sd = binary.readSkeletonDataFile(skel_path);
...
delete skA; delete skB;      // 骨架删了
// delete sd;                // ← 忘了
```

三轮后堆从 716 KB 涨到 1.07 MB 且继续增长。补上 `delete sd` 后，
每轮删除后都回到 405,288 B，**完全稳定**。

#### 2) 分配器 O(n²)：解析 7239 ms → 158.6 ms（46 倍）

第一版分配器：
* 分配：从表头首次适配扫描
* 释放：为找前驱**从表头全表扫描**

解析 spineboy 会产生 **7000+ 个块**，于是解析退化为 O(n²)：

```
[DUO] it1 load 7384.7 ms (tex 134.0 + read 8.9 + parse 7239.6, blocks 7048)
```

改成**双向链表 + 漫游指针（next-fit）**后：

```
[DUO] it1 load 222.1 ms (tex 55.9 + read 7.6 + parse 158.6, blocks 7224)
```

* 释放：O(1)（有 prev 指针，前后邻都能直接合并）
* 分配：从上次成功位置继续，绕过已满的头部区域

#### 3) 顺带修的：DWT 32 位回绕

帧计时原本用"循环开始/结束各取一次 `DWT->CYCCNT`"，在 480 MHz 下
**每 8.9 秒回绕一次**，4 秒的循环经常跨越回绕点，算出 1929 fps 这种假数据。
改成逐帧累加（单帧 < 40 ms，不会回绕）。

### 观察

* 双角色时 `raster` 是全分辨率的 2.25 倍（15.3 → 37 ms 里 raster 30.4），
  因为两个角色各占半屏，像素总数与单角色全屏相当，但**三角形数翻倍**。
* 半分辨率下 `present` 涨到 8.61 ms（面积翻倍），已成为第二大开销。
  它是 D-cache 写分配的内存带宽问题，下一步优化点。

## 纹理格式：ARGB1555 与 ARGB4444 双支持

### 转换

```bash
# 硬边素材（快，1 bit alpha）
python DSH/middleware/png_to_raw.py hero.png hero.raw --fmt 1555 --pma

# 柔边素材（发光/软阴影，4 bit alpha）
python DSH/middleware/png_to_raw.py hero.png hero.raw --fmt 4444 --pma
```

`--pma` 做反预乘（spine 图集通常是预乘的，光栅器按直通 alpha 混合）。

文件头里的 `format` 字段：`1 = ARGB1555`、`2 = ARGB4444`。
**目标端自动识别**，文件名不用改，切换只需重新转换覆盖 .raw。

### 目标端

* `RawTexture` 新增 `fmt` 字段（来自文件头）
* 加载器接受 1 或 2，打印实际格式
* `draw_commands` 按纹理格式选择 `RASTER_FMT_ARGB1555` / `RASTER_FMT_ARGB4444`

### 性能差异（栅格器基准，-O3）

| 场景 | ARGB1555 | ARGB4444 |
|---|---|---|
| 全屏四边形 · 常量色 | **11.20 Mpx/s** | 5.54 Mpx/s |
| 16×12 网格 · 逐顶点色 | **6.82 Mpx/s** | 3.46 Mpx/s |

4444 慢的原因是每像素多 3 次 `×17` 的 4→8 位展开（约 1.97 倍）。

### 选型建议

| 素材 | 格式 |
|---|---|
| 角色主体、武器、UI（硬边） | **ARGB1555** |
| 发光、软阴影、羽化边缘 | ARGB4444 |
| 完全不透明 | RGB565 + 色键（最快） |

渲染器支持**逐纹理**格式，所以同一个场景里可以混用：主体页 1555、特效页 4444。

### 两种格式的实测对比（双角色，各 3 轮，每轮重新加载）

| 场景 | ARGB1555 | ARGB4444 | 差异 |
|---|---|---|---|
| 全分辨率 × 2 角色 | 37.10 ms / **27.0 fps** | 47.07 ms / **21.2 fps** | −21% |
| 半分辨率 × 2 角色 | 25.45 ms / **39.3 fps** | 27.34 ms / **36.6 fps** | −7% |
| 加载 | 222 ms | 223 ms | 持平 |
| 三轮一致性 | 27.0 / 27.0 / 27.0 | 21.2 / 21.2 / 21.2 | 稳定 |
| 删除后堆 | 405,288 B | 405,288 B | 无泄漏 |

半分辨率下两者差距只有 7%，因为此时开销已被 `present`（放大 8.6 ms）分摊。

### 画质差异

4444 的 4 位 alpha 让柔边内容（本例的护目镜镜片）呈现半透明过渡，
1 位 alpha 的 1555 则把它当全不透明。需要柔边就用 4444，其余用 1555。

## 计时器：最终修复（uint32 溢出）

### 根因

相位累加器用的是 `uint32_t`。一次 240 帧的循环里，单个相位累加超过 2³² 就回绕：

```
阈值 = 2^32 / 480000 Hz / 240 帧 = 37.28 ms/帧
```

* **半分辨率**：最大相位 draw = 31.5 ms < 37.28 → 不回绕 → 分段和 = 帧时间 ✓（看起来一切正常）
* **全分辨率**：draw 实际 82.5 ms > 37.28 → **回绕成 3.13 ms** ✗

帧总时间用的是 `uint64_t`，所以一直是对的；于是出现"帧时间 = 独立时钟，
但分段相加差 74 ms"的诡异现象。差值正是被 2³² 取模吃掉的部分。

### 修复

所有相位累加器 `uint32_t → uint64_t`，打印时统一转 `double`。

### 修复后的真实数据（celestial-circus 双角色，每轮 4 s = 240 帧）

| 阶段 | 全分辨率 | 半分辨率 |
|---|---|---|
| anim | 1.01 ms | 1.00 ms |
| build（render + bbox） | 4.13 ms | 4.25 ms |
| clear | 4.23 ms | 1.02 ms |
| **draw（光栅）** | **82.51 ms** | **31.52 ms** |
| present（放大） | 0.35 ms | 8.72 ms |
| wait / setfb | 0 | 0 |
| **sum** | **92.23 ms** | **46.52 ms** |
| **frame / wall** | 92.23 / 92.22 ✓ | 46.52 / 46.52 ✓ |

### 由此得到的真实结论

1. **光栅是绝对瓶颈**：占全分辨率 89%、半分辨率 68%。
2. **present 只有 8.72 ms（19%）**，优化它的上限收益有限。
3. **光栅速率反常地低**：
   * 全分辨率 92 k 像素 / 82.5 ms = **1.1 Mpx/s**
   * 半分辨率 23 k 像素 / 31.5 ms = **0.73 Mpx/s**
   * 而合成基准是 **6.8 Mpx/s**（spineboy 用的是 512 KB 小图集）
4. **原因几乎肯定是 4 MB 图集撑爆 16 KB D-Cache**：每个纹素都是一次 SDRAM
   随机访问，局部性极差。半分辨率只降到 2.6 倍（而非 4 倍），说明
   **每三角形 setup 成本**在小像素量下开始显现。

### 优化优先级因此改变

* ~~先优化 present~~ → **先优化纹理访问局部性**
* 方向：导出时降图集尺寸（scale 0.5 → 1 MB）、图集分页常驻、纹理 swizzle
* present 优化仍有价值（8.72 ms → 3~4 ms），但它是第二优先

## 图集尺寸对光栅性能的影响（实测）

同一套 celestial-circus 素材，只改变导出缩放：

| 导出设置 | 页数 × 尺寸 | 纹理内存 | 加载 | 全分辨率双角色 | 半分辨率双角色 |
|---|---|---|---|---|---|
| `scale 0.5`（原） | 2 × 1024×1024 | **4.0 MB** | 587 ms | 92.23 ms / **10.8 fps** | 46.52 ms / **21.5 fps** |
| `scale 0.25`（新） | 1 × 1024×512 | **1.0 MB** | 262 ms | 57.90 ms / **17.3 fps** | 36.30 ms / **27.5 fps** |
| 变化 | 页数 −1，内存 −75% | | −55% | **+60%** | **+28%** |

### 光栅阶段拆解

| 阶段 | 4 MB 图集 | 1 MB 图集 | 变化 |
|---|---|---|---|
| draw（全分辨率） | 82.51 ms | **48.40 ms** | −41% |
| draw（半分辨率） | 31.52 ms | **21.93 ms** | −30% |
| present | 8.72 ms | 8.30 ms | 持平 |
| clear / build / anim | 5.2 / 4.2 / 1.0 | 4.0 / 4.1 / 1.0 | 基本持平 |
| **合计（全）** | 92.23 ms | **57.90 ms** | −37% |
| **合计（半）** | 46.52 ms | **36.30 ms** | −22% |

### 光栅速率（每画 100 k 像素需要多少毫秒）

| 图集 | 全分辨率 | 半分辨率 |
|---|---|---|
| 4 MB | 1.1 Mpx/s | 0.73 Mpx/s |
| **1 MB** | **1.9 Mpx/s** | **1.06 Mpx/s** |
| 512 KB（spineboy 对照） | — | 7.4 Mpx/s |

**结论**：纹理内存是光栅性能的一阶因素。从 4 MB 降到 1 MB，
全分辨率帧率直接 **+60%**，而且**没有改一行代码**——纯粹是素材侧的决定。

### 半分辨率的收益因此变小

4 MB 图集时半分辨率还能提升 2.16 倍（46.52 vs 92.23 ms 折算），
1 MB 时只有 1.60 倍（57.90 → 36.30 ms）。因为此时 `present`（8.3 ms）
在 36.3 ms 里占了 23%，成为第二大成本。

**这意味着：图集越小，present 优化越值得做。**

## present 优化（实测）

### 第一步：先量帧缓冲写入上限

600 KB 顺序填充到帧缓冲，三种 MPU 属性 × 两种存储宽度：

| MPU 属性 | 32 位存储 | 64 位存储 | 缓存冲刷 |
|---|---|---|---|
| write-back（原行为） | 4.16 ms (144 MB/s) | 4.01 ms (150 MB/s) | 0.28 ms |
| non-cacheable | 4.16 ms (144 MB/s) | 3.58 ms (168 MB/s) | 0.28 ms |
| **write-through** | 4.16 ms (144 MB/s) | **3.52 ms (170 MB/s)** | 0.28 ms |

**结论出乎意料**：MPU 属性对 32 位存储**完全没有影响**（都是 144 MB/s），
所以"write-allocate 导致流量翻倍"这个假设**是错的**。真正有效的是：

* **64 位存储**：150 → 170 MB/s（+13%）
* **SDRAM 写上限约 170 MB/s**

### 第二步：重写 `raster_upscale2x`

原实现有两个问题：

1. 内层循环同时写第 `2y` 行和第 `2y+1` 行 → **两条交替的写流**，SDRAM 行地址来回跳
2. 每像素只做 32 位写

新实现：

* **按目标行顺序**，一行写完再写下一行 → 单条顺序写流
* **64 位宽存**：2 个源像素压成 4 个输出像素，一次 8 字节写
* 8 字节对齐前缀 / 奇数尾像素用 32 位处理

### 结果

| 指标 | 优化前 | 优化后 | 变化 |
|---|---|---|---|
| **present（半分辨率）** | 8.30 ms | **5.45 ms** | **−34%** |
| 半分辨率帧时间 | 36.30 ms | **33.53 ms** | −7.6% |
| **半分辨率帧率** | 27.5 fps | **29.8 fps** | **+8.4%** |
| 全分辨率帧时间 | 57.90 ms | 57.95 ms | 持平（预期内） |

### 两个"看起来有用但实测无效"的优化

| 尝试 | 基准预期 | 实测 |
|---|---|---|
| MPU 改 non-cacheable / write-through | −12% | **0**（真实负载下无差别） |
| 去掉冗余缓存冲刷 | 省 0.3 ms | **0**（忽略不计） |

两者都保留了（写穿仍然开着一件事：数据直达 SDRAM，LTDC 看到的一定是最新内容）。

### present 现在的位置：**带宽受限**

```
流量 = 读 192 KB（低分辨率缓冲）+ 写 600 KB（帧缓冲）= 792 KB
5.45 ms → 145 MB/s，上限 170 MB/s → 已用掉 85%
```

**继续优化 present 只能靠减少流量**，不是改实现。

### 下一步：把放大合并进光栅器

如果光栅器直接按 2×2 块写帧缓冲，就能消掉低分辨率缓冲的**写 192 KB + 读 192 KB**：

| 方案 | 流量 | 预计 |
|---|---|---|
| 现在（两遍） | 192 写 + 192 读 + 600 写 = 984 KB | 27.5 ms 光栅 + 5.45 ms present |
| 合并（一遍） | 600 写 | ~24.5 ms 光栅 + 0 |
| 预计收益 | | **−3 ms ≈ +9%** |

风险：光栅器写 2×2 块时是三角形内分散写，SDRAM 行命中率不如顺序放大，
实际收益可能打折。需要实测验证。

### 修复：64 位打包字节序错误（竖向条纹 bug）

重写放大函数时踩的坑：小端机下 `uint64` 的**低位对应低地址**。

```cpp
/* 错：输出变成 [b, b, a, a] —— 每对源像素左右颠倒 */
packed = (a << 48) | (a << 32) | (b << 16) | b;

/* 对：输出 [a, a, b, b] */
packed = a | (a << 16) | (b << 32) | (b << 48);
```

**症状**：半分辨率模式下出现大量竖向条纹模糊（2 像素周期的细节错位）。
全分辨率不受影响，因为不走放大路径。

**验证方法**（比肉眼看更可靠）：

| 检查 | 正确 2× 最近邻应有 | 实测 |
|---|---|---|
| 扫描线游程长度 | 全为 2 | **0% 奇数长度** ✓ |
| 偶数列与右邻列相同 | 100% | **100.0%** ✓ |

## 对外 API（已规范化）

### 分层

| 层 | 文件 | 职责 |
|---|---|---|
| **API 层** | `User/spine_api.h` / `.cpp` | 资产、实例、每帧绘制调度（本文档重点） |
| 平台层 | `User/spine_platform.h` / `.cpp` | 分配器、资源区、纹理加载、FatFs、混合模式映射 |
| 光栅层 | `Middlewares/RASTER/raster2d.*` | 扫描线光栅器（与平台无关） |
| 动画层 | `Middlewares/SPINE` | spine-cpp 4.3 |

测试/基准代码（`spine_test.cpp`）不再承担生产职责，只保留基准与演示。

### 完整接口

```c
/* ---- 资产：加载一次，可被多个实例共享 ---- */
spine_asset_t *spine_asset_load(const char *skel_path, const char *atlas_path);
void           spine_asset_free(spine_asset_t *asset);
int            spine_asset_anim_count(spine_asset_t *asset);
const char    *spine_asset_anim_name(spine_asset_t *asset, int index);
uint32_t       spine_asset_texture_bytes(spine_asset_t *asset);

/* ---- 实例 ---- */
spine_instance_t *spine_instance_create(spine_asset_t *asset);
void              spine_instance_destroy(spine_instance_t *in);

void spine_instance_play(spine_instance_t *in, const char *anim, int loop, int track);
void spine_instance_stop(spine_instance_t *in, int track);
void spine_instance_set_speed(spine_instance_t *in, float speed, int track);
void spine_instance_set_time(spine_instance_t *in, float seconds, int track);

void spine_instance_set_position(spine_instance_t *in, float x, float y);   /* 屏幕像素 */
void spine_instance_set_scale(spine_instance_t *in, float scale);           /* 世界单位->像素 */
void spine_instance_set_flip(spine_instance_t *in, int flip_x, int flip_y);
void spine_instance_set_tint(spine_instance_t *in, uint32_t rgba8888);
void spine_instance_set_alpha(spine_instance_t *in, uint8_t alpha);

void spine_instance_update(spine_instance_t *in, float dt);                 /* 动画 + 物理 */
int  spine_instance_get_bounds(spine_instance_t *in,
                               float *x0, float *y0, float *x1, float *y1); /* 屏幕包围盒 */

/* ---- 绘制 ---- */
void spine_draw_begin(int divisor);                  /* 1=全分辨率 2=半分辨率 */
void spine_instance_draw(spine_instance_t *in);      /* 调用顺序 = 层级 */
void spine_draw_end(void);
int  spine_draw_queue_count(void);

/* ---- 世界重力 ---- */
void  spine_world_set_gravity(float gx, float gy);
float spine_world_get_gravity_x(void);
float spine_world_get_gravity_y(void);
int   spine_world_instance_count(void);
```

### 调用序列

```c
spine_asset_t *asset = spine_asset_load("/spine/hero.skel", "/spine/hero.atlas");
spine_instance_t *hero  = spine_instance_create(asset);
spine_instance_t *enemy = spine_instance_create(asset);      /* 同一资产，独立状态 */

spine_instance_play(hero,  "swing",     1, 0);
spine_instance_play(enemy, "wing-flap", 1, 0);

/* 用包围盒把角色摆到想要的位置 */
float x0, y0, x1, y1;
spine_instance_get_bounds(hero, &x0, &y0, &x1, &y1);
float s  = 220.0f / (y1 - y0);
float cx = (x0 + x1) * 0.5f, cy = (y0 + y1) * 0.5f;
spine_instance_set_scale(hero, s);
spine_instance_set_position(hero, 210.0f - cx * s, 250.0f - cy * s);

while (1) {
    float dt = frame_dt();
    spine_instance_update(hero,  dt);
    spine_instance_update(enemy, dt);

    spine_draw_begin(2);                  /* 半分辨率 */
    spine_instance_draw(hero);
    spine_instance_draw(enemy);           /* 后画 = 在上层 */
    spine_draw_end();
}
```

### 实测（真机，celestial-circus，两个实例）

```
[API] asset loaded: 7 animations | 1 textures
[API] animations: eyeblink eyeblink-long stars swing wind-idle wing-flap wings-and-feet
[API] texture bytes: 1048576
[API] bounds=(-755,-1809)-(577,556) scale=0.093
[API] 300 frames | 19.71 ms/frame (50.7 fps) | instances=2 queue=2
[API] after free: instances=0
[API] RESULT PASS
```

### 集成时踩的两个坑（都已修）

#### 1) `heap_init()` 非幂等 → 同一块内存分配两次 → HardFault

`SpineMcuExtension` 是**惰性构造**的，其构造函数里调用 `heap_init()`。
API 层若先用 `spine_heap_alloc` 分配了 asset 结构体，随后第一次 `new` spine 对象
触发扩展构造 → `heap_init()` **重置整个堆** → asset 所在块被判为空闲 → 下一个对象
拿到**同一地址**，把 asset 覆盖 → 虚表被打坏 → 跳到 PC=0x28 的 HardFault。

修复：`heap_init()` 幂等（`g_head != nullptr` 直接返回）。

> 旧测试代码第一次分配就是 spine 对象，扩展先初始化，所以这个 bug 被掩盖了很久。

#### 2) 半分辨率下实例变换没除以 divisor

实例的 `position/scale` 是**屏幕像素**，但绘制目标是 `1/divisor` 大小的低分辨率缓冲。
不换算的话，角色位置和尺寸都会 ×2，且脏矩形算在屏幕空间 → 只画出一部分。

修复：`draw_one` 与 bbox 累加都乘 `1/divisor`（新增 `g_d.inv_divisor`）。
`get_bounds` 仍返回**屏幕坐标**（对调用者最直观）。

## 平台抽象层（PAL）：换平台只需重写一个文件

### 文件

| 文件 | 内容 |
|---|---|
| `User/plat/plat_cfg.h` | 屏幕尺寸、缓冲数、对齐、能力开关（**移植时改这个**） |
| `User/plat/plat.h` | 六组接口声明（库与硬件之间唯一的耦合面） |
| `User/plat/plat_stm32h7.c` | H743 实现（**换平台时重写这个**） |

### 六组接口

```c
/* 1. 内存：库内分配器可移植，平台只提供两段内存 */
void plat_mem_pools(void **heap, size_t *heap_size,
                    void **arena, size_t *arena_size);

/* 2. 文件系统 */
int  plat_file_open(plat_file_t **f, const char *path);
int  plat_file_read(plat_file_t *f, void *buf, size_t bytes, size_t *got);
int  plat_file_size(plat_file_t *f, size_t *bytes);
void plat_file_close(plat_file_t *f);

/* 3. 显示 */
int   plat_display_w(void);
int   plat_display_h(void);
int   plat_fb_count(void);
void *plat_fb_addr(int index);
void  plat_fb_present(void *fb);
void  plat_fb_set_cache_mode(int mode);     /* 0=写回 1=非缓存 2=写穿 */
int   plat_fb_need_cache_clean(void);

/* 4. 缓存 */
void plat_cache_clean(void *addr, size_t bytes);
void plat_cache_invalidate(void *addr, size_t bytes);

/* 5. 时间 */
uint32_t plat_now_ms(void);
uint64_t plat_now_us(void);
void     plat_delay_ms(uint32_t ms);

/* 6. 日志 */
void plat_log(const char *fmt, ...);
```

共 **17 个函数**，全部是"每帧 / 每纹理"级别调用，**没有一个在每像素循环里**。

### 改造后库内的依赖情况

| 文件 | 之前 | 现在 |
|---|---|---|
| `spine_platform.cpp` | 写死 `0xC0200000` / `0xC0A00000`、FatFs `f_open/f_read` | `plat_mem_pools` / `plat_file_*` |
| `spine_api.cpp` | `LTDC->CFBAR`、`SRCR=VBR`、`while(VBR)` | `plat_fb_present` |
| `raster2d.cpp` | `SCB_CleanInvalidateDCache_by_Addr` | `plat_cache_clean` |
| `spine_test.cpp` | MPU 配置 | `plat_fb_set_cache_mode` |

库里已**没有任何绝对地址、没有寄存器访问、没有文件系统 API**。

### 验证：封装前后性能完全一致

| 测试 | 封装前 | 封装后 |
|---|---|---|
| 全分辨率双角色 | 57.85 ms / 17.3 fps | **57.89 ms / 17.3 fps** |
| 半分辨率双角色 | 33.46 ms / 29.9 fps | **33.65 ms / 29.7 fps** |
| API 双实例 | 19.71 ms / 50.7 fps | **19.80 ms / 50.5 fps** |
| 加载 | 320 / 263 ms | 319.9 / 263.1 ms |
| 驱动 + 光栅 + TGX 自检 | 全 PASS | 全 PASS |

### 移植到新平台的步骤

1. 复制 `plat_cfg.h`，改屏幕尺寸 / 缓冲数 / 对齐
2. 新写 `plat_<platform>.c`，实现那 17 个函数
3. 把新文件加进工程
4. **库代码一行不改**

ESP32-P4 的对应实现要点：

| 接口 | P4 上怎么做 |
|---|---|
| `plat_mem_pools` | `heap_caps_malloc(MALLOC_CAP_SPIRAM)` 拿池 |
| `plat_file_*` | VFS `fopen/fread` |
| `plat_fb_*` | `esp_lcd_rgb_panel` 的 `num_fbs` + vsync 回调 |
| `plat_cache_*` | `esp_cache_msync(..., C2M)` |
| `plat_now_us` | `esp_timer_get_time()` |
| `plat_fb_set_cache_mode` | 空实现（ESP 无 MPU 帧缓冲属性） |

## RTOS 适配（PLAT_USE_RTOS 宏开关）

### 一套代码两种模式

`plat_cfg.h` 里：

```c
#define PLAT_USE_RTOS           0    /* 0 = 裸机，1 = RTOS */
#define PLAT_ENABLE_MEM_LOCK    0    /* 1 = 多任务共享 spine 堆时打开 */
```

**裸机时所有 OS 钩子都是空宏**，库代码可以无条件调用，不需要 `#if`：

```c
#define plat_os_mem_lock()    do { } while (0)
#define plat_os_sem_take(s, ms)  do { } while (0)
```

### 两种模式的差异

| 行为 | 裸机（PLAT_USE_RTOS=0） | RTOS（=1） |
|---|---|---|
| 等垂直回扫 | `while (SRCR & VBR) {}` 轮询占满 CPU | 等 LTDC 重装中断的信号量，**让出 CPU** |
| 延时 | `HAL_Delay` 忙等 | `vTaskDelay` |
| 毫秒时基 | `HAL_GetTick` | `xTaskGetTickCount` |
| 分配器 | 无锁 | `PLAT_ENABLE_MEM_LOCK` 时用递归互斥 |

### RTOS 下必须做的三件事

#### 1) HAL 时基挪出 SysTick

FreeRTOS 独占 SysTick。若 HAL 还用 SysTick，`HAL_Delay` / `HAL_GetTick` 会与调度冲突
（表现为随机卡死或延时不准）。

> CubeMX：`SYS → Timebase Source` 改成 **TIM6** 或 **TIM7**。

#### 2) 加入 OS 适配文件

把 `User/plat/plat_os_freertos.c.template` 改名为 `plat_os_freertos.c` 加入工程，
并把 `PLAT_USE_RTOS` 改成 1。它实现 `plat_os_sem_*` / `plat_os_delay_ms` /
`plat_os_tick_ms` / `plat_os_mem_lock`。

#### 3) LTDC 中断不要重复定义

`plat_stm32h7.c` 在 RTOS 模式下已经定义了 `LTDC_IRQHandler`（寄存器重装中断 →
给信号量）。工程里不要再定义同名函数。

### 任务划分建议

```
┌────────────────────────────────────────────┐
│  Render Task    优先级 高                   │
│    update(dt) → draw_begin/draw/end        │
│    （draw_end 里等 vsync 会让出 CPU）       │
├────────────────────────────────────────────┤
│  Loader Task    优先级 低                   │
│    spine_asset_load()（SD 读较慢，别占着渲染）│
├────────────────────────────────────────────┤
│  GUI / 逻辑 Task 优先级 中                  │
└────────────────────────────────────────────┘
```

**内存所有权规则（二选一）：**

| 方案 | 说明 |
|---|---|
| **推荐**：加载只在 Loader 任务、渲染只在 Render 任务，用队列交接 | 零锁开销 |
| 允许多任务调用 spine API | 打开 `PLAT_ENABLE_MEM_LOCK = 1`（递归互斥，每次分配多几微秒） |

### 已验证 / 未验证

| 项 | 状态 |
|---|---|
| 裸机模式（PLAT_USE_RTOS=0） | ✅ 真机验证，性能与封装前完全一致（57.87 / 33.57 ms） |
| RTOS 模式（PLAT_USE_RTOS=1） | ⚠️ 代码路径已写好并加了宏隔离，但**工程里还没有 FreeRTOS**，未编译验证 |
| LTDC 重装中断 → 信号量 | ⚠️ 同上，需要接入 FreeRTOS 后实测 |

> 打开 RTOS 前建议先做一件事：确认 `LTDC->ISR` 的 `RRIF` 位确实会置位
> （用轮询版跑一帧，读一次 ISR，即可验证中断源可用）。
