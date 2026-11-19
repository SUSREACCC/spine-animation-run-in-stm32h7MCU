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

## 功能展示程序（spine_demo）

### 用法

自检全部通过后自动进入循环演示（`selftest.c` 末尾）：

```c
#if SPINE_RUN_DEMO
    spine_demo_run();      /* 不返回 */
#endif
```

开关在 `User/spine_demo.h`：`#define SPINE_RUN_DEMO 1`。
设为 0 则恢复原来的"打印心跳"模式。

### 六个场景（循环，约 90 秒一轮）

| # | 场景 | 演示内容 | 时长 |
|---|---|---|---|
| 1 | 双实例 | 两个角色不同动画（swing / wing-flap）+ tint | 6 s |
| 2 | 变换组合 | 正常 / 水平翻转 / 半透明(alpha=110) / 着色 | 5 s |
| 3 | 重力旋转 | 重力绕一圈，物理驱动形变 | 7 s |
| 4 | 动画巡演 | 依次播放骨架里的每个动画 | 3 s × N |
| 5 | 分辨率对比 | 同一场景先全分辨率再半分辨率，打印两者 fps | 6 s |
| 6 | 压力测试 | 8 个实例、4 种动画、交替翻转 | 5 s |

### 实测结果

| 场景 | 结果 |
|---|---|
| 场景切换与动画 | ✅ 正常工作（4 秒内 113,857 像素变化） |
| 双实例 / 变换 / 重力 | ✅ 画面正确 |
| 帧率（半分辨率，角色 200 px 高） | ≈ 50 fps |

### 已知问题：屏幕 HUD 指示器不显示

设计上在屏幕顶部画 6 个场景指示格、底部画进度条（纯 CPU 矩形填充），
**实测这些像素没有出现**。已经排除的方向：

* `fb_mpu_set(2)` 写穿模式下 CPU 写入应直达 SDRAM ✓
* 三块缓冲都写了一遍 ✓
* `demo_hud_flush()` 确认被调用（每 30 帧 + 场景切换）✓

**未定位的原因**：可能是 API 的 `spine_draw_begin/draw_end` 在内部对缓冲做了
整体操作（初始化时全清），或是 HUD 写入与光栅写入的次序问题。

**当前方案**：场景名、fps、实例数等信息**全部走串口 printf**，
屏幕只显示角色本身。这是可用的（不影响演示内容），但不是最初设计的样子。

### 附带发现的两个板级坑

1. **`lcd_fill()` 走 DMA2D**，与 CPU 的 D-Cache 不是同一视图，
   在自定义帧缓冲上填充会"看起来没生效"。
2. **`lcd_show_string()` 用 `mode=0`**（同时画背景），背景色取自全局
   `g_back_color`（默认**白色**）→ 白字白底，等于看不见。
   用前必须 `g_back_color = 0x00000000`。

## 覆盖层 API（overlay）

### 设计

HUD / UI / 调试信息必须和 spine 层走**同一条渲染管线**，否则会出现：
* `lcd_fill()` 走 DMA2D，与 CPU 绘制的 D-Cache 视图不一致
* `lcd_show_string()` 用 `mode=0`，背景色取自全局 `g_back_color`（默认白色）
* 板级函数不知道我们有 3 块缓冲和半分辨率缩放

### 接口

```c
/* 屏幕像素坐标，闭区间；在 spine_draw_begin() 与 spine_draw_end() 之间调用 */
void spine_overlay_rect (int x0, int y0, int x1, int y1, uint16_t color565);
void spine_overlay_frame(int x0, int y0, int x1, int y1, int thick, uint16_t color565);
void spine_overlay_text (int x, int y, const char *ascii, uint16_t color565);
int  spine_overlay_count(void);     /* 诊断：本帧排队的操作数 */
```

### 三条硬性规则（都是踩坑换来的）

| 规则 | 原因 |
|---|---|
| **画进全部帧缓冲**，不能只画当前 dst | 三缓冲下每块缓冲 3 帧才轮到一次，只画 dst 会让三块显示不同内容 → 闪烁 |
| **文字用全分辨率坐标**，不跟随 divisor | 画进半分辨率缓冲再放大会糊 |
| **矩形必须真的填满** | 曾经有个 `if (n == 1) { 画一个像素; return; }` 的早退分支，导致清屏带只清了一个点，旧文字永远擦不掉 → 重影/混叠 |

### 字库

自带 5×7 点阵（`User/spine_font.h`，由 `DSH/middleware/gen_font.py` 生成并逐字验证），
默认放大 2 倍（10×14 像素，字符步进 12）。不依赖板级 `asc2_1608`。

生成器自带校验：

```bash
python DSH/middleware/gen_font.py --check     # 用 ASCII art 打印样例字符串
```

### 实测

| 项 | 结果 |
|---|---|
| 文字清晰度 | ✅ 全分辨率，边缘锐利 |
| 三缓冲一致性 | ✅ 顶栏/底栏内容完全一致（不像素级比对通过） |
| 闪烁 | ✅ 无 |
| 重影/混叠 | ✅ 修复后无 |
| 帧率影响 | 约 −0.3 ms/帧（三缓冲各画一次 HUD） |

### 用法示例

```c
spine_draw_begin(2);

for (i...) spine_instance_draw(list[i]);

/* 覆盖层 */
spine_overlay_rect(0, 0, 799, 23, 0x0000);
spine_overlay_text(180, 4, "3/6 GRAVITY ROTATE", 0xFFFF);
spine_overlay_rect(4, 476, 4 + prog, 478, 0x001F);

spine_draw_end();
```

### 实现位置

* 声明：`User/spine_api.h`
* 实现：`User/spine_api.cpp`（`ov_rect_scaled` / `ov_text_at` / `spine_overlay_flush`）
* 字库：`User/spine_font.h`
* 挂钩点：`spine_draw_end()` 在实例绘制、放大之后，逐个缓冲绘制覆盖层

## 测试组织（宏开关 + 模块拆分）

### 开关文件：`User/test_cfg.h`

所有测试由宏控制，**默认只跑当前关心的项目**：

| 宏 | 默认 | 内容 | 耗时 |
|---|---|---|---|
| `TEST_DRIVERS` | **1** | SDRAM / LCD / QSPI / SD / FATFS 自检 | ~5 s |
| `TEST_RASTER` | 0 | raster2d 回归 | ~2 s |
| `TEST_FBBENCH` | 0 | 帧缓冲写带宽基准 | ~5 s |
| `TEST_SHEET` | 0 | 素材总览 | ~10 s |
| `TEST_GRAVITY` | 0 | 物理重力方向 | ~20 s |
| `TEST_DUO` | 0 | 双角色压力（全/半分辨率各 2 轮） | ~60 s |
| `TEST_API_DEMO` | 0 | spine_api 最小示例 | ~20 s |
| **`TEST_IK`** | **1** | **IK 目标驱动（spineboy）** | ~6 s |
| `TEST_DEMO` | 0 | 6 场景循环展示（不返回） | ∞ |
| `TEST_HEARTBEAT` | 1 | 心跳打印 | — |

> `TEST_DRIVERS` 必须为 1：`test_lcd()` 内部执行 `lcd_init()`，关掉就没有显示初始化。

### 效果

| 配置 | 上电到出结果 |
|---|---|
| 全开（旧） | ~4 分钟 |
| 默认（只 IK） | **~15 秒** |

### 模块拆分

| 文件 | 内容 |
|---|---|
| `User/selftest.c` | 启动流程 + 驱动自检 + 按宏调度各测试 |
| `User/spine_test.cpp` | 素材总览 / 双角色 / 重力 / 帧缓冲基准 |
| `User/spine_ik_test.c` | **IK 目标驱动测试（独立模块）** |
| `User/spine_demo.c` | 6 场景循环展示 |
| `User/test_cfg.h` | 所有开关 |

IK 测试的签名（可直接复用）：

```c
int spine_ik_test(const char *skel, const char *atlas,
                  const char *anim, int hold_frames, int visual);
/* 1 = PASS，0 = FAIL，-1 = 素材里没有 IK */
```

---

## IK 目标驱动（实测）

### API

```c
int         spine_instance_ik_count(spine_instance_t *in);
const char *spine_instance_ik_name(spine_instance_t *in, int index);
int         spine_instance_ik_bone_count(spine_instance_t *in, const char *ik_name);
float       spine_instance_ik_mix(spine_instance_t *in, const char *ik_name);
int         spine_instance_set_ik_mix(spine_instance_t *in, const char *ik_name, float mix);

int  spine_instance_set_ik_target(spine_instance_t *in, const char *ik_name,
                                  float world_x, float world_y);
int  spine_instance_get_ik_target(spine_instance_t *in, const char *ik_name,
                                  float *wx, float *wy);
int  spine_instance_get_ik_tip(spine_instance_t *in, const char *ik_name,
                               float *wx, float *wy);
void spine_instance_clear_ik(spine_instance_t *in);
```

坐标一律是**骨架世界坐标**（spine 单位），不是屏幕像素。

### 实现要点

1. 覆盖值在 `AnimationState::apply()` **之后**、`updateWorldTransform()` **之前**写入目标骨骼的
   applied pose（`BonePose::setX/setY`，配合 `worldToParent()` 做世界→父空间换算）。
   放早了会被动画轨道覆盖。
2. `IkConstraint::getBones()` 返回的是 `_constrainedPose` 子对象，**不能 static_cast 回 Bone**；
   要拿 `Bone*` 必须经 `IkConstraintData::getBones()[i]->getIndex()` 查 `Skeleton::getBones()`。
3. `IkConstraint::update()` 第一句是 `if (mix == 0) return;` —— mix 为 0 的约束完全不动。

### spineboy 素材实测

7 个 IK 约束：

| # | 名字 | 链长 | mix | 末端残差 |
|---|---|---|---|---|
| 0 | board-ik | 1 | 1.00 | 197.9 |
| 1 | front-leg-ik | 2 | 1.00 | 0.5 |
| 2 | rear-leg-ik | 2 | 1.00 | **0.0** |
| 3 | front-foot-ik | 1 | 1.00 | 0.2 |
| 4 | rear-foot-ik | 1 | 1.00 | 0.3 |
| 5 | aim-torso-ik | 1 | 1.00 | 411.1 |
| 6 | aim-ik | 1 | 0.00 | 393.9 |

> 残差 = |末端位置 − 目标位置|。2 骨 IK（腿）残差接近 0 说明在正常跟随；
> 1 骨 IK（board/aim）目标超出骨长时够不到，残差大是正常的。
> `aim-ik` 的 mix 是 0，所以完全不动。

驱动 `rear-leg-ik` 的目标 +40 世界单位后：

```
target (-145.7,-76.8) -> (-105.7,-76.8), set=1
tip moved 46.05, residual 40.00 -> 7.52
RESULT PASS
```

## 触摸交互 IK（实机可用）

### 硬件

| 项 | 值 |
|---|---|
| 触摸 IC | **GT1158**（驱动白名单原本没有，需把 `"1158"` 加进 `gt9xxx_init` 的 ID 判断） |
| 软 IIC | PB12(SCL) / PB13(SDA) |
| RST | PB14 |
| INT | PH7 —— **被 SDRAM 占用**，不可用（从 SDRAM 引脚掩码里去掉会直接 SDRAM 自检失败） |

> 因为 INT 拿不到，`tp_scan()` 的按键门控（`T_PEN == 0`）不可靠；
> 交互测试改为**直接轮询 GT1158 的 I2C 寄存器**：
> `0x814E`（bit7 = 有新数据，低 4 位 = 触摸点数）、`0x8150`（第一个点的 x/y 低高字节），
> 读完后写 0 到 `0x814E` 清标志。

### 坐标换算

```c
world_x = (screen_x - instance_x) / instance_scale;
world_y = (screen_y - instance_y) / instance_scale;
```

实例的 `position/scale` 是屏幕像素，所以反算就是一次平移 + 缩放。

### 交互模块

`User/spine_ik_interactive.c`

```c
int spine_ik_interactive(const char *skel, const char *atlas,
                         const char *ik_name, int max_seconds);
/* max_seconds = 0 -> 永久运行；1 = 收到过触摸，-1 = 没触摸，0 = 失败 */
```

每帧：
1. 轮询触摸 → 换算世界坐标 → `spine_instance_set_ik_target()`
2. 目标锁住最后一次点击位置（防止动画轨道把目标拉走）
3. `update(dt)` 用**真实帧间隔**（不是固定 1/60，否则慢帧时动画变慢动作）
4. 渲染 + 顶栏显示 `IK 名 / 剩余时间 / 帧率 / 末端位置`

### 实测

```
[IK]  IK constraints: 7
[IK]  subject: #2 rear-leg-ik (residual 0.0)
[IK]  tip moved 46.05, residual 40.00 -> 7.52   => PASS
[IKT] rear-leg-ik t=0s 63.7fps tip=(-90,-50) waiting
[IKT] first touch (412,268) -> world (74.2,-385.3)
```

- 帧率 **63.7 fps**（半分辨率 + 覆盖层）
- 点击屏幕后角色右腿跟随点击点，串口打印首次触摸的坐标换算

### 触摸驱动 IK 的三种状态（常态播放 / 按下跟随 / 松开恢复）

```
        ┌───────────── 按下 ─────────────┐
        │                                ▼
     [IDLE] ◄── 混合结束/clear_ik ── [ACTIVE]
        ▲                                │
        └────────── [BLEND] ◄──── 抬手 ───┘
```

| 状态 | 行为 |
|---|---|
| **IDLE** | **完全不覆盖** IK 目标，动画全权驱动（常态播放） |
| **ACTIVE** | 每帧用触点覆盖目标；动画其余部分照常播放 |
| **BLEND** | 松开后 8 帧内把覆盖点插值回动画目标，然后 `clear_ik()` 回到 IDLE |

实现要点：

1. `gt_poll()` 改为**三态**：`1`=按下、`0`=无新报文、`-1`=抬手
   （原来 `0` 同时表示"无数据"和"抬手"，无法区分）
2. 报文间隔抖动用 **120 ms 超时**兜底，避免把间隔误判成抬手
3. 松开瞬间多调一次 `spine_instance_update()`，让动画把目标写回去，
   再用 `get_ik_target()` 取"动画此刻的目标"作为插值终点
4. 混合帧数由 `TEST_IK_RELEASE_BLEND` 控制（0 = 立即恢复）

实测串口：

```
[IKT] ACTIVE  touch (618,281) -> world (473.8,-367.4)
[IKT] BLEND   8 frames -> back to animation
[IKT] IDLE    animation resumed
[IKT] rear-leg-ik t=24s 63.6fps state=IDLE tip=(205,-301)
[IKT] rear-leg-ik t=25s 63.6fps state=IDLE tip=(182,-355)
```

`state=IDLE` 时 `tip` 随走路动画变化 ✓；`state=BLEND` 出现在松开后的 8 帧内 ✓。

### 踩坑：松开后运动范围整体平移

**现象**：触摸松开后，腿没有回到原来 0°–20° 的摆动范围，而是在 40°–60° 之间摆动 —— 像是加了一个常量偏移。

**原因**：`spine_instance_set_ik_target()` 把目标写进了目标骨骼的 **applied pose**；
而 `spine_instance_clear_ik()` 原先只清空覆盖表，**没有把那根骨骼还回去**。
spineboy 的 IK 目标骨骼不被动画驱动（没有 timeline 写它），
所以最后一次写入的局部坐标永久留在骨架上 → 整段运动范围被平移。

**修复**（`spine_api.cpp`）：

1. 覆盖槽新增 `base_lx / base_ly / captured`：**首次**覆盖前记录目标骨骼的局部姿态
2. `clear_ik()` 先把 `base_lx/base_ly` 写回目标骨骼，再清空覆盖表

```c
/* clear_ik 里 */
for (i...) {
    if (slot->ik && slot->captured) {
        BonePose &p = slot->ik->getTarget().getAppliedPose();
        p.setX(slot->base_lx);
        p.setY(slot->base_ly);
    }
}
memset(in->ik, 0, sizeof(in->ik));
```

**回归检查**（`spine_ik_test.c` 自动跑）：

```
[IK] after clear_ik: tip=(-91.2,-112.0) dist to pushed target 38.0
[IK] restore OK (tip left the pushed target)
[IK] RESULT PASS
```

判定：`clear_ik()` 之后末端到"被推过去的目标"的距离必须明显变大
（保持时 4.32 → 还原后 38.0），否则说明偏移泄漏。

## 动画衔接 API（过渡 / 进度接回）

### 背景

spine-cpp 的 `AnimationStateData` 默认 `defaultMix = 0`，所以 `spine_instance_play()`
切动画是**硬切**。要平滑过渡必须显式设置 mix。

### 接口

```c
void  spine_instance_set_default_mix(spine_instance_t *in, float seconds);
int   spine_instance_set_mix(spine_instance_t *in, const char *from, const char *to, float seconds);
float spine_instance_get_time(spine_instance_t *in, int track);
const char *spine_instance_current_anim(spine_instance_t *in, int track);
int   spine_instance_seek(spine_instance_t *in, float seconds, int track);
```

### 关键实现细节

1. **`set_mix` 先查存在性**：`AnimationStateData::setMix(name, name, d)` 内部是
   `assert(from != NULL)`，名字写错会直接断言死机。所以先 `findAnimation()` 判空，
   再调用 `Animation&` 重载；名字不存在返回 0。
2. **`seek` 与 `set_time` 的区别**：`set_time()` 会把 `timeScale` 置 0（定格），
   接回播放进度时不能用它；`seek()` 保留原 timeScale。
3. **TrackEntry 生命周期**：`AnimationState` 默认会在动画播完时
   `disposeTrackEntry()`，而我们缓存了 `TrackEntry*`（get_time/seek 需要）。
   直接缓存会**悬空指针 → HardFault**。所以：
   - `create()` 里 `state->setManualTrackEntryDisposal(true)`
   - `play()` 把上一代条目放进 `retire[]`，且**只有确认它不在任何混合链里**
     （沿 `getMixingFrom()` 走一遍）才回收
   - `stop()` / `destroy()` 显式 `disposeTrackEntry()`

### 典型用法：触摸切动画再切回

```c
float saved = spine_instance_get_time(in, 0);

spine_instance_set_default_mix(in, 0.20f);      /* 200 ms 过渡 */
spine_instance_play(in, "touch_idle", 0, 0);    /* 触摸时 */

/* 松开 */
spine_instance_play(in, "walk", 1, 0);
spine_instance_seek(in, saved, 0);              /* 接回原进度，不从头开始 */
```

### 实机验证（`spine_anim_test.c`，上电自动跑）

```
[ANIM] A=walk  B=idle
[ANIM] set_mix(walk->idle)=1  set_mix(bad)=0 (expect 1 / 0)
[ANIM] playing walk  time=0.500
[ANIM] switched to idle (expect idle)
[ANIM] seek back to 0.500 -> 0.500
[ANIM] RESULT PASS
```

### 没做的：`add_anim`（排队下一段）

底层能用，但实机验证时发现：排队动画接管后 spine 会 `setTrack(i, next)`，
旧条目从 `next` 链上被摘掉，而我们缓存的指针看不到这次切换
（`current_anim()`/`get_time()` 会一直报旧动画，时间冻结在切换点）。
spine-cpp 没有公开"取某轨当前条目"的接口，没法干净地跟上，
所以**没有把它放进公开 API**。需要排队功能时，建议改用动画事件或自己管理时间轴。

## 脚本动画序列测试（walk → idle → aim → death）

`User/spine_anim_seq.c`，上电自动跑，四段串联：

| 阶段 | 动画 | 时长 | 循环 | 交互 |
|---|---|---|---|---|
| 1 | walk | 5 s | 是 | — |
| 2 | idle | 5 s | 是 | — |
| 3 | **aim** | 10 s | 是 | **触摸驱动 `aim-ik`** |
| 4 | death | 5 s | **否（单次）** | — |

段间过渡 0.30 s（`set_default_mix`）。

### 实测数据（spineboy 素材）

```
[SEQ] phase 1/4  walk  loop=1  5 s  dur=1.00
[SEQ] phase 2/4  idle  loop=1  5 s  dur=1.67
[SEQ] phase 3/4  aim   loop=1 10 s  dur=0.00  touch->aim-ik
[SEQ] phase 4/4  death loop=0  5 s  dur=4.93
[SEQ]   t=1s  anim=death  track=1.00  applied=1.00
[SEQ]   t=4s  anim=death  track=4.01  applied=4.01
[SEQ] RESULT DONE
```

关键点：

1. **aim 的动画时长是 0**（单帧姿态动画）—— 这段的"动作"完全靠触摸驱动 `aim-ik`（该约束在素材里 `mix=0`，进入该段时临时设为 1，离开时还原）。
2. **death 时长 4.93 s**，`loop=0` 时 `applied` 单调涨到 4.93 后停住（不会回到 0），证明**只播一次**。
3. `track`（trackTime）会一直涨，`applied`（getAnimationTime）才是真正的动画时间 —— 判定"是否循环"要看后者。

### 新增的小 API

```c
float spine_instance_anim_time(in, int track);      /* 实际动画时间（循环会回绕） */
float spine_instance_anim_duration(in, int track);  /* 动画总时长 */
```

用于区分"播放进度"和"动画时长"，也是判定单次播放的依据。

### 松手抽搐的成因与修复

**现象**：松开手指时姿态会抖一下。

**成因**（测试模块原来的实现）：

```
松手那一帧：
  clear_ik()             → 腿瞬间回到动画姿态
  update()               → 一次没有覆盖的更新
  get_ik_target()        → 读出动画目标
  ...同一帧继续 draw      → 按"动画姿态"画了一次
下一帧：
  BLEND 从触点重新开始    → 又跳回触点
```

两次跳变就是抽搐。

**修复**（`spine_ik_interactive.c` / `spine_anim_seq.c`）：

1. 捕获动画目标后**立刻恢复覆盖**，并 `continue` **跳过本帧渲染** ——
   丢 1 帧（约 16 ms）不可见，但消除了双跳变；
2. 固定 8 帧线性插值改为**指数平滑**（时间常数 `TEST_IK_RELEASE_TAU_MS`，默认 120 ms）：
   `target += (anim - target) * (1 - e^(-dt/τ))`；
3. 残差 < 2 个世界单位（或超过 0.6 s）时再 `clear_ik()`，
   此时切换已看不出来。

`TEST_IK_RELEASE_TAU_MS` 调小 = 回得更快，调大 = 更黏。

> 说明：Spine 里的物理约束（PhysicsConstraint 的 inertia/strength/damping）
> 无法用来平滑这种运行时覆盖 —— 覆盖写在 `apply()` 之后、`updateWorldTransform()` 之前，
> 而物理约束在 `Skeleton::update(dt)` 推进、`updateWorldTransform()` 应用，
> 两者作用在同一根骨骼上会互相覆盖。

### IK 覆盖的两种释放方式

| API | 行为 | 用在什么时候 |
|---|---|---|
| `spine_instance_clear_ik(in)` | 还原目标骨骼到首次覆盖前的姿态，再清覆盖表 | 交互彻底结束、不再回动画 |
| `spine_instance_release_ik_keep_pose(in)` | **只清覆盖表，不动骨骼姿态** | 交给"两段动画 + 过渡"的方案接管 |

#### 为什么需要 keep_pose

`clear_ik()` 会把目标骨骼瞬间弹回旧值 —— 如果紧接着启动动画过渡，这一下就是可见的抽搐。

用 `release_ik_keep_pose()` 时，目标骨骼停在手指最后的位置，随后播正常动画并设 mix：

```c
/* 按下：交互动画（腿与目标骨骼都没有时间轴） */
spine_instance_play(in, "aim_noleg", 1, 0);
spine_instance_set_ik_mix(in, "leg-ik", 1.0f);
/* 每帧 */
spine_instance_set_ik_target(in, "leg-ik", wx, wy);

/* 松开：交给动画混合，不需要手写插值 */
spine_instance_release_ik_keep_pose(in);
spine_instance_set_default_mix(in, 0.25f);
spine_instance_play(in, "walk", 1, 0);
```

正常动画里目标骨骼的 timeline 会把目标从"手指最后的位置"平滑拉回正常目标，
腿自然回位。

#### 前提

正常动画必须**驱动目标骨骼**（walk 里腿的 IK target 要有 timeline）。
如果它不驱动，目标会停在手指位置 → 腿一直偏着（这种情况要用 `clear_ik()`）。

> 该 API 已实现并通过编译，**尚未在硬件上验证**（需要一份"腿无时间轴"的交互动画素材）。

### 触摸作为"额外动作"：mix 淡入淡出（`spine_anim_seq.c` 的 aim 段）

与"接管现有 IK"（腿跟手）不同，这类交互的 IK **平时不参与**（`mix = 0`），
只在触摸时启用，松手再淡出 —— 部位自然回到动画姿态，不需要目标插值。

```
IDLE --按下--> FADE_IN --mix=1--> ACTIVE --松手--> FADE_OUT --mix=0--> IDLE
```

| 参数 | 默认 | 说明 |
|---|---|---|
| `SEQ_IK_FADE_IN_MS` | **150 ms** | 按下时 mix 0→1 |
| `SEQ_IK_FADE_OUT_MS` | **250 ms** | 松手时 mix 1→0 |

实现要点：

1. 阶段开始时 `set_ik_mix(name, 0.0f)` —— 保证平时不参与
2. 按下：每帧 `set_ik_target(手指)` 并按时间把 mix 升到 1
3. 松手：目标**保持不变**，只把 mix 降下来；
   mix 到 0 时 `clear_ik()`，此时目标已无影响，所以不会跳变
4. mix 由我们自己累加（不从引擎读回），避免每帧查询开销

### 两种交互的对照

| | 额外动作（aim 段） | 接管现有 IK（腿） |
|---|---|---|
| IK 平时 mix | 0 | 1（走路需要它） |
| 按下 | mix 淡入 + 驱动目标 | 直接驱动目标 |
| 松手 | **mix 淡出** | **目标指数平滑**回动画目标 |
| 素材要求 | 额外 IK，无时间轴 | 复用现有 IK |

### 重要坑：动画的 IK Mix 时间轴会覆盖运行时设置

**现象**：触摸时 IK 瞬间全量生效（没有渐变），松手也不复位。

**诊断**（串口同时打印"我们写的"和"求解器读的"）。`spine_instance_ik_mix_applied()`
读的是 `IkConstraint::getAppliedPose().getMix()`，也就是 `IkConstraint::update()` 用的那个：

```
mix=0.00/1.00     ← 我们写 0，求解器读到 1
```

**原因**：`aim` 动画带 **IK Mix 时间轴**，每帧 `AnimationState::apply()` 都会把
`aim-ik` 的 mix 写回 1。应用层在 `update()` 之外设置的值，下一帧就被覆盖。

**修复**（`spine_api.cpp`）：

1. `set_ik_mix()` 不再直接写 pose，而是**存进实例的 `mix[]` 表**
2. `apply_ik_overrides()`（运行在 `apply()` 之后、`updateWorldTransform()` 之前）
   每帧把表里的值写进 **pose 和 applied pose 两边**
3. `ik_mix()` 优先返回表里的值（与求解器一致）

修复后：

```
mix=0.00/0.00     ← 两边一致
```

> 教训：凡是"运行时想覆盖动画驱动的属性"，都必须写在 `AnimationState::apply()`
> **之后**。IK 目标如此，IK 混入也如此。之前 IK 目标没问题，是因为目标骨骼没有时间轴；
> 而 `aim-ik` 的 mix 有时间轴。

### 第二个坑：共用目标骨骼的约束必须一起淡入淡出

诊断时发现 `aim-ik` 与 `aim-torso-ik` 的 **target 是同一根骨骼**（都是 `(302.4,-569.7)`）。

只淡出 `aim-ik` 时，`aim-torso-ik`（mix 恒为 1）会**立刻**跟随新的目标点 →
看起来仍然是"瞬间跳变"。

修法：把共用目标的约束放进同一个淡入淡出组：

```c
{ "aim", 1, 10, "aim-ik", "aim-torso-ik" },   /* 两个一起淡 */
```

### 模拟触摸（便于验证）

`SEQ_SIM_TOUCH`（默认 1）：aim 段第 2~6 秒自动模拟一次按压，目标点绕圈。
不触摸也能验证渐变链路：

```
t=1s  mix=0.00/0.00  st=0  tip=(56,-338)   ← 休息
t=2s  mix=0.01/0.01  st=1                  ← 淡入开始
t=3s  mix=0.51/0.51  st=1  tip=(35,-361)   ← 一半
t=4s  mix=1.00/1.00  st=2  tip=(-96,-364)  ← 满
t=7s  mix=0.54/0.54  st=3  tip=(40,-366)   ← 淡出
t=9s  mix=0.00/0.00  st=0  tip=(56,-338)   ← 完全复位
```

验证完把 `SEQ_SIM_TOUCH` 改成 0 即可用真实触摸。
