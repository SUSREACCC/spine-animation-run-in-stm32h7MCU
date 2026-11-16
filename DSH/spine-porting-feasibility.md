# STM32H743 移植 Spine 运行时 —— 技术可行性评估报告

| 项 | 内容 |
|---|---|
| 报告版本 | **V2（修订版）**，2026-11-14 16:05 |
| V1 → V2 变更 | 纳入用户确认的 6 项决策；改用**本地** `spine-cpp` 复核（版本配对已证实）；重新实测编译/链接体积（修正 V1 的 295 KB 为 205/381 KB）；新增特性覆盖矩阵、内存模型、性能基准协议 |
| 评估对象 | `thirdPartyComponents/spine-c`（4.3）、`thirdPartyComponents/tgx-main`（TGX 1.1.4）、`D:\gitCode\spine_runtimes\spine-cpp`（4.3, commit `405f4329`） |
| 目标平台 | 慧勤智远 STM32H743IIT6 V1.3 + **4.3" IPS 800×480 RGB 屏**，MDK **AC6.7（不变更）** |
| 评估性质 | 只读侦察 + 真实工具链编译/链接验证；**未修改任何项目源文件** |

---

## 0. 结论

**结论：可行。** 且 V1 中最大的两个不确定性（spine-cpp 缺件、版本配对）**已消除**——本地 spine-cpp 与工程内 spine-c 同源同版本，实测 227 个源文件全部编译通过。

| 维度 | 结论 | 关键数据 |
|---|---|---|
| 版本配对 | ✅ 已证实 | 工程内 `spine-c` 与 `D:\gitCode\spine_runtimes\spine-c`（branch `4.3` @ `405f4329`）**逐字节完全一致**（diff 0 差异）|
| 编译 | ✅ 227/227 通过 | AC6.7，`-std=c++1z -fno-exceptions -fno-rtti`，0 error |
| 代码体积 | ✅ 宽裕 | **RO 205 KB**（默认移除未引用段，走 `.skel` 路径）/ **381 KB**（`--no_remove` 全保留）；2 MB Flash 用 10–19% |
| 静态 RAM | ✅ 极小 | RW 88 B、ZI ≈ 2.5 KB（不含帧缓冲）；骨架数据全在 SDRAM 堆 |
| 屏幕/带宽 | ✅ 匹配 | 4.3" 800×480 RGB565，帧缓冲 **750 KB**，双缓冲 1.5 MB @ 32 MB SDRAM |
| 必需特性 | ✅ 核心齐备 | IK / 网格变形 / 裁剪蒙版 均在 spine-cpp 内实现，且 spine-c 已生成对应 C API |
| 唯一实质风险 | ⚠️ **渲染吞吐未实测** | 目标帧率未定 → 本报告给出基准协议与决策表，Phase 0（0.5 天）出结论 |
| 工作量 | ≈ 10 人日 | 见 §9 |

> **一句话**：移植本身已无技术障碍；剩下的全部风险集中在“480 MHz 软件光栅能跑多少像素”，而这只需半天基准测试就能定量回答。

---

## 1. 已确认的决策（本轮输入）

| # | 决策 | 对方案的影响 |
|---|---|---|
| D1 | 屏幕 = **4.3 寸 RGB**（WKS43WV067-WCT，4.3" IPS，800×480，16/24-bit RGB，CTP GT1151Q @ I²C） | 走 LTDC + SDRAM 帧缓冲；帧预算按 800×480 计 |
| D2 | **有 Spine 4.3.x 正版编辑器授权** | 合规风险关闭；可导出 `.skel`/`.atlas` |
| D3 | 待播放动画尺寸**未定** | 报告给出“像素覆盖 → 帧率”决策表（§8.4），便于定尺寸 |
| D4 | **沿用当前 ARM-MDK（5.24 / AC6.7）** | 语言标准锁 `-std=c++1z`；无结构化绑定；已验证可行，见 §4 |
| D5 | 目标帧率**未定，需实测评估** | Phase 0 定义可复现基准协议 + 量化判据（§8） |
| D6 | 本地 spine-cpp 位于 `D:\gitCode\spine_runtimes` | 已验证同源，见 §3.1 |
| D7 | 首期必须支持：**IK、网格变形、裁剪蒙版**，其余后续添加 | 三者均属核心已实现 + 通用三角渲染即可覆盖，见 §5 |

---

## 2. 硬件基线（已核实）

来源：板级手册 PDF（pdftotext 提取）、`WKS43WV067-WCT_SPEC` 模块规格书、板级例程 `实验11 SDRAM` / `实验12 LTDC` 源码。

| 项目 | 规格 | 对 Spine 的意义 |
|---|---|---|
| MCU | STM32H743IIT6，Cortex-M7 **480 MHz**，LQFP176 | 决定软件光栅吞吐 |
| FPU | **DP-FPU**（fpv5-d16），MDK 工程 `FPU3(DFPU)` | 全浮点可行，无需定点化 |
| Cache | L1 I-Cache 16 KB + D-Cache 16 KB | **帧率关键**：纹理/帧缓冲命中率 |
| Flash | 2 MB 内部 + 16 MB QSPI（W25Q128，可内存映射） | 代码 205 KB；资源可放 QSPI 或拷入 SDRAM |
| SRAM | 1060 KB（AXI 512 KB + DTCM 128 KB + SRAM1-3 288 KB + SRAM4 64 KB） | 栈/堆/条带缓冲；**装不下 800×480 帧缓冲** |
| SDRAM | **32 MB** W9825G6KH-6I @ FMC Bank5 `0xC0000000`，16-bit，**110 MHz**（≈220 MB/s 理论） | 帧缓冲 + 图集 + 骨架堆的唯一落点 |
| 显示 | **4.3" IPS 800×480**，16/24-bit RGB 并口，LTDC 驱动；例程默认 **RGB565**，`LTDC_FRAME_BUF_ADDR = 0xC0000000` | 单帧 800×480×2 = **750 KB** |
| 触摸 | CTP **GT1151Q**（I²C），独立于显示 | 可选交互，不影响动画主链 |
| 加速 | DMA2D、DCMI、QSPI、SDMMC | DMA2D 可清屏/搬运层 |

**带宽预算**：LTDC @60 Hz 扫描 RGB565 ≈ **46 MB/s**；SDRAM 理论 220 MB/s → CPU 可用 ≈ **170 MB/s**。
**这一条直接约束渲染策略**：双线性 ARGB8888 采样最坏情况 16 B/像素（4 纹素 × 4 B），8 Mpx/s 就要 128 MB/s——所以 D-Cache 命中率与纹理布局（局部性）是性能设计的核心，方案见 §8.2。

---

## 3. 软件组件评估

### 3.1 spine 版本配对（V1 的阻塞项已消除）

`D:\gitCode\spine_runtimes` 是 **git 检出**：branch `4.3`，HEAD = `405f43295b5832e86d9df3a80beb6bc9df772312`（2026-11-10）。

| 检查 | 结果 |
|---|---|
| `spine-cpp` 版本宏 | `SPINE_MAJOR_VERSION 4` / `SPINE_MINOR_VERSION 3` |
| `spine-cpp` 规模 | 88 个 `.cpp` + 113 个 `.h` |
| 工程内 `spine-c` vs 本地 git `spine-c` | **`diff -rq` 输出 0 行——逐字节完全一致** |
| 异常/RTTI 依赖 | `throw` / `dynamic_cast` / `typeid` 共 **0 处** |

⇒ 不需要联网下载、不需要改版本，**直接引用本地 `spine-cpp` 即可**。V1 的“R2 版本漂移”风险关闭。

### 3.2 spine-c 4.3 的本质（重要认知）

spine-c 4.3 **不是独立 C 运行时**，而是 spine-cpp 的 C-API 包装层：

- `src/generated/*.cpp`（134 个）全部 `#include <spine/spine.h>`，并用 `new (__FILE__, __LINE__)` 走 spine-cpp 自定义分配器；
- `src/extensions.cpp` 提供 spine-cpp 必需的 `spine::getDefaultExtension()`；
- ⇒ **实现层必须以 C++ 编译**；上层可用纯 C 调用（全部 `extern "C"`）。

渲染接口（正是我们需要的抽象）：

```
spine_atlas_load_callback(atlasText, dir, loadFn, unloadFn)    // 纹理加载回调由我们提供
spine_skeleton_data_load_binary(atlas, skelBytes, len, path)   // .skel 二进制（推荐）
spine_skeleton_drawable_create / update(dt) / render()
  → spine_render_command 链表：
     positions(x,y) / uvs / colors(u32 RGBA) / darkColors /
     indices(u16) / blendMode(NORMAL|ADDITIVE|MULTIPLY|SCREEN) / texture / next
```

`RenderCommand` 的字段与 TGX 的 `drawTexturedGradientTriangle` 一一对应（顶点位置、UV、每顶点 RGBA、纹理），仅 `darkColors`（双色着色）无直接对应。

### 3.3 TGX 1.1.4

| 项 | 结论 |
|---|---|
| 定位 | 纯 C++17、**零外部依赖**、只写内存帧缓冲、硬件无关 | 
| H7 支持 | ✅ `tgx_config.h` 有专用分支：`__ARM_ARCH_7EM__ && (__ARM_FP & 0x8)`（H7 的 DP-FPU） |
| 关键能力 | 纹理三角形 + 双线性 + **每顶点颜色/alpha** + **自定义混合算子** + `Image` 视图（天然裁剪窗口） |
| 混合语义（已读 `Shaders.h`） | 纹理色 × 插值顶点色（RGB 与 **A 都相乘**）→ 再混合 ⇒ 与 Spine 的 straight-alpha 顶点着色器语义一致 |
| 裁剪 | 不需要 scissor：spine 的 `SkeletonClipping` 在 CPU 侧完成多边形裁剪 + 重三角化，输出已是裁剪后三角形 |
| 语言门槛 | `if constexpr`（141 处）→ 需 C++17 语义；AC6.7 的 `-std=c++1z` 通过 |
| 唯一编译坑 | AC6 libcxx `<math.h>` 导致 `abs(int)` 二义 → `-include <stdlib.h>` 解决（**不改 TGX 源码**）|
| 能力缺口 | ① 双色着色（darkColors）无对应着色器 ② 无索引三角形（逐三角形调用，开销可忽略）|

---

## 4. 实测证据（本轮，用**你的**代码重跑）

工具链：`D:\MDK5\ARM\ARMCLANG\bin\armclang.exe` = **ARM Compiler 6.7 / MDK Plus 5.24**（D4：不变更）。
编译选项：`--target=arm-arm-none-eabi -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard -std=c++1z -O2 -fno-exceptions -fno-rtti -DNDEBUG`。

| # | 实验 | 结果 |
|---|---|---|
| 1 | `-std=c++17` | ❌ `invalid value`；**仅接受 `-std=c++1z`**（C++17 草案级，无结构化绑定） |
| 2 | **227 个源文件全量编译**（spine-cpp 88 + spine-c 生成层 134 + extensions 1 + TGX 探针/兼容层 4） | ✅ **0 error / 0 fail** |
| 3 | 链接（`armlink` 默认移除未引用段，`entry=app`） | ✅ **RO 199,420 + RO Data 10,552 = 209,972 B（205 KB）**；RW 88 B；ZI ≈ 2.5 KB |
| 4 | 链接（`--no_remove`，强制保留全部） | **RO 390,252 B（381 KB）** |
| 5 | TGX 纹理三角形单 TU | 代码 **3,288 B** |
| 6 | 集成驱动（atlas 回调 lambda + drawable + 渲染命令遍历） | ✅ 编译通过 |
| 7 | 需要的兼容补丁 | **2 处**：`strdup`（ARM C 库无，自实现 10 行）、`abs(int)` 二义（`-include stdlib.h`） |

**关于 205 KB 与 381 KB 的差别（V1 数据修正）**：`armlink` **默认移除未被引用的输入段**。
- 只走 `.skel` 二进制路径时，JSON 解析器（`SkeletonJson.o` 53 KB）等不会被引用 → **205 KB**，这是推荐配置的真实占用；
- 若强制全保留（`--no_remove`）或链接器配置不同 → **381 KB**。
- ⇒ 报告统一采用 **205 KB（实测）/ 381 KB（上界）** 两个数；V1 的 295 KB 已废弃。

**实测结构体尺寸（ARM 32-bit，用于 §6 内存模型）**：

| 类型 | 字节 | 类型 | 字节 |
|---|---|---|---|
| `BoneData` | 160 | `Skeleton` | 212 |
| `SlotData` | 128 | `SkeletonData` | 224 |
| `RegionAttachment` | 112 | `AtlasRegion` | 160 |
| `MeshAttachment` | 188 | `Animation` | 104 |
| `ClippingAttachment` | 112 | `TrackEntry` | 188 |
| `IkConstraint` | 92 | `EventData` | 80 |
| `Skin` | 92 | `AnimationState` | 132 |

**可选的体积优化开关**（后续按需）：
- 去掉 JSON 路径：只解码 `.skel` → 已体现在 205 KB；
- `-DSPINE_NO_CPP_RT`：去掉 `<unordered_map>` 依赖（Debug 用），AC6.7 下少一个 libc++ 头；
- 链接 `--remove`（默认）+ `-ffunction-sections`：进一步剥离未用函数。

---

## 5. 特性覆盖矩阵（首期必做的三项已确认可行）

| 特性 | 核心运行时（spine-cpp） | C API（spine-c 已生成） | 渲染侧需求 | 首期结论 |
|---|---|---|---|---|
| **IK 约束** | ✅ `IkConstraint.cpp` | `spine_ik_constraint_*` | 无（只影响骨骼姿态） | ✅ 直接可用 |
| **网格变形** | ✅ `DeformTimeline` / `MeshAttachment` | `spine_deform_timeline_*` / `spine_mesh_attachment_*` | 通用「任意 UV 三角形」→ TGX 已具备 | ✅ 直接可用 |
| **裁剪蒙版** | ✅ `ClippingAttachment` + `SkeletonClipping`（CPU 裁剪+重三角化） | `spine_clipping_attachment_*` | 无（输出已裁剪三角形） | ✅ 直接可用 |
| 路径约束 / 变换约束 | ✅ | ✅ | 无 | 顺带可用 |
| 多皮肤 / 换装 | ✅ `Skin` | `spine_skin_*` | 只换纹理与附件 | 顺带可用 |
| 事件（音效/回调） | ✅ `EventData` / `AnimationState` events | `spine_animation_state_events_*` | 无 | 顺带可用 |
| **双色着色 darkColors** | ✅ | ✅ | ❌ TGX 无对应着色器 | ⚠️ 首期忽略（多数项目不用）；需要时自写 rasterizer 分支 |
| 混合模式 ADDITIVE / MULTIPLY / SCREEN | ✅ | ✅ | ✅ TGX 自定义 blend 算子可覆盖 | ✅ 需实现 4 个算子 |
| 预乘 alpha（PMA） | ✅ | ✅ | 需按图集导出设置选择混合算子 | ✅ 二选一，二阶段定 |

> 关键判断：**首期三项必需特性都不需要新增运行时能力**——它们要么只影响骨骼姿态（IK），要么已经被 spine 自己算完（变形顶点、裁剪三角形）。移植侧的工作量集中在「渲染桥 + 资源管线 + 验证」，而不是「实现特性」。

---

## 6. 内存模型（基于实测 sizeof + 典型角色推算）

**固定占用（不受资产影响）**

| 项 | 大小 | 位置 |
|---|---|---|
| 帧缓冲（双缓冲 800×480 RGB565） | 2 × 750 KB = **1.5 MB** | SDRAM |
| 代码 | 205 KB | 内部 Flash |
| 静态 RW/ZI | ≈ 2.5 KB | 内部 SRAM |
| TGX 纹理三角形代码 | 3.3 KB | 内部 Flash |

**随资产增长的部分（典型 35 骨骼 / 45 槽位 / 60 附件 / 6 动画角色）**

| 组成 | 估算 |
|---|---|
| `BoneData` + `Bone` 运行时对象 | 35 × (160 + ≈180) ≈ **12 KB** |
| `SlotData` + `Slot` | 45 × (128 + ≈100) ≈ **10 KB** |
| 附件（Region/Mesh） | 60 × 112–188 ≈ **9 KB**（网格顶点/UV 数组另计） |
| `Animation` + 时间轴（主要项） | 6 动画 × 15 轴 × 30 帧 × ≈84 B/帧 ≈ **220 KB** |
| 解析临时缓冲（.skel 读取期） | 与文件同量级，解析完即释放 |
| **合计** | **0.3 – 1 MB**（大角色/多动画可达 2–3 MB） |

**图集**：1024×1024 ARGB8888 = **4 MB**/页；2048×2048 = 16 MB（32 MB SDRAM 下仍可行但建议避免）。

**放置策略（建议）**

| 资源 | 建议位置 | 理由 |
|---|---|---|
| `.skel` 二进制 | QSPI（内存映射）→ 解析前拷到 SDRAM 临时区 | QSPI 直接解析慢；拷贝一次更稳 |
| 图集（ARGB8888） | **开机拷入 SDRAM** | 采样命中率远高于 QSPI；4 MB 代价可接受 |
| 骨架运行时对象 | SDRAM 专用堆（`SpineExtension` 子类） | 避免碎片化内部 SRAM、便于统计 |
| 帧缓冲 ×2 | SDRAM @ `0xC0000000` | 与例程一致 |
| 栈 / TGX 临时 | DTCM/AXI SRAM | 零等待、不受 LTDC 争用 |

⇒ **总 SDRAM 需求 ≈ 1.5 + 4 + 1 ≈ 6.5 MB / 32 MB**，余量充足。

---

## 7. 系统架构

```
┌────────────────────────── Application (C/C++) ───────────────────────────┐
│ main: HAL_Init → 480MHz → MPU/D-Cache → SDRAM → LTDC → (可选)GT1151 触摸    │
│ anim_task(16.6ms): spine_skeleton_drawable_update()                      │
│                    spine_skeleton_drawable_render()                      │
│                    spine_tgx_render(cmds, fb)   // 渲染桥                 │
└──────────┬──────────────────────────────────────────────┬────────────────┘
           │ C-API                                        │ 逐 RenderCommand
   ┌───────▼─────────┐                          ┌─────────▼──────────────────┐
   │ spine-c (C API) │                          │ renderer bridge（自研）     │
   │ spine-cpp 4.3   │                          │ 索引→三角 / 4 种 blend 算子 │
   └───────┬─────────┘                          └─────────┬──────────────────┘
           │ atlas 回调 + SpineExtension(SDRAM 堆)          │ drawTexturedGradientTriangle
   ┌───────▼─────────┐                          ┌─────────▼──────────────────┐
   │ 图集 ARGB8888   │◄──────── 采样 ───────────│ TGX (C++17, header-only 主体)│
   │ in SDRAM        │                          │ Image<RGB565> dst           │
   └─────────────────┘                          │ Image<RGB32>  tex           │
                                                └─────────┬──────────────────┘
                                                ┌─────────▼──────────────────┐
                                                │ 800×480 RGB565 帧缓冲 ×2    │
                                                │ @0xC0000000 (SDRAM)         │
                                                └─────────┬──────────────────┘
                                                          │ LTDC 扫描 + 换页
                                                     ┌────▼────┐
                                                     │ 4.3" 屏 │
                                                     └─────────┘
```

**三个必须提前定死的设计点**

1. **Cache 一致性**：LTDC 读 SDRAM 帧缓冲，CPU 写同一块。二选一——
   (a) MPU 把帧缓冲区设为 **non-cacheable**（简单、稳、慢约 15–30%）；
   (b) 保持 cacheable + 每帧 `SCB_CleanDCache_by_Addr`（快，但要保证 32 B 行对齐与调用时机）。
   **建议**：Phase 0 两种都测，用数据决定（这正好是基准测试的一项）。
2. **纹理格式**：ARGB8888（质量最好、带宽 16 B/px）vs RGB565+点采样（带宽 8 B/px，无平滑 alpha）。
3. **分配器**：用 `SpineExtension` 子类把 Spine 的所有分配导向 SDRAM 堆，实现「开机一次性加载 + 零运行时分配」。

---

## 8. 性能评估方案（目标帧率未定 → 用数据定）

### 8.1 帧预算

| 目标 | 预算 | 备注 |
|---|---|---|
| 60 fps | **16.7 ms** | 含骨架更新(<1 ms) + 渲染 + 换页 |
| 30 fps | **33.3 ms** | 中小角色舒适区 |
| 24 fps | 41.7 ms | 动画观感下限 |

### 8.2 带宽模型（决定优化方向）

| 采样方式 | 每像素外部读 | 8 Mpx/s 时带宽 | 判断 |
|---|---|---|---|
| 点采样 ARGB8888 | 4 B | 32 MB/s + 写 16 MB/s | 最省 |
| **双线性 ARGB8888** | 最坏 16 B（4 纹素） | **128 MB/s** + 写 16 | 接近 220 MB/s 上限 → **依赖 D-Cache 命中** |
| 双线性 RGB565 | 最坏 8 B | 64 MB/s + 写 16 | 推荐折中 |
| 双线性 + 命中 L1D（16 KB） | 摊销后 ≈4–8 B | 32–64 MB/s | 目标状态 |

结论：**能不能跑满帧率，一半看光栅指令数，一半看纹理局部性**。因此：
- 图集页按角色部件排布（相邻三角形 UV 连续）→ 命中率显著提升；
- 角色渲染区域小 → 纹素复用率高 → 实际带宽远低于最坏值。

### 8.3 Phase 0 基准测试协议（半天，可复现）

| # | 测什么 | 怎么测 | 判据 |
|---|---|---|---|
| B1 | 纯填充率 | TGX `fillScreen`/大三角形，DWT→CYCCNT 计 N 次 | 得 Mpx/s 上界 |
| B2 | 双线性纹理三角形 | 真实图集页 + 512 个三角形/帧，测 Mpx/s | **核心指标**（决定一切） |
| B3 | 同上但点采样 | 同上，关闭双线性 | 与 B2 对比得双线性开销占比 |
| B4 | Cache 策略对比 | 帧缓冲 non-cacheable vs cacheable+clean | 选实现方案 |
| B5 | 骨架更新耗时 | `spine_skeleton_drawable_update()` ×1000 次平均 | 应 < 1 ms |
| B6 | 端到端 | 用真实资产播 30 s，统计平均/最差帧时间 | 得实际 fps |

**测量手段**：DWT->CYCCNT（`CoreDebug->DEMCR |= TRCENA`），串口输出 CSV；每项跑 3 次取中位数。
**输出**：`Mpx/s`、`ms/帧`、`最大连续帧时间` —— 三个数就能定架构。

### 8.4 决策表（拿到 Mpx/s 后直接查表）

渲染时间 = 覆盖像素 ÷ 吞吐。下表为不同吞吐/角色尺寸下的**单帧渲染耗时（ms）**：

| 角色覆盖像素 | 4 Mpx/s | 6 Mpx/s | 8 Mpx/s | 12 Mpx/s |
|---|---|---|---|---|
| 60 k（半身 300×400，≈50% 覆盖） | 15.0 | 10.0 | 7.5 | 5.0 |
| 180 k（全身 500×600，≈60% 覆盖） | 45.0 | 30.0 | 22.5 | 15.0 |
| 384 k（800×480 满屏） | 96.0 | 64.0 | 48.0 | 32.0 |

**判读**：
- 若 B2 测出 **≥ 8 Mpx/s** → 半身/全身角色 30–60 fps 直接达标，无需优化；
- 若落在 **4–8 Mpx/s** → 中小角色 30 fps 可用，全身/满屏需启用优化阶梯；
- 若 **< 4 Mpx/s** → 需先做 §8.5 的 1–3 项优化再评估（此时应优先怀疑 Cache 配置而非算法）。

### 8.5 优化阶梯（按性价比，逐级启用）

| 级 | 手段 | 预期收益 | 代价 |
|---|---|---|---|
| 1 | D-Cache 策略调优 + 图集 UV 局部性 | 1.5–2.5× | 配置工作量 |
| 2 | 关双线性（点采样） | ≈2× | 边缘质量下降 |
| 3 | 纹理改 RGB565/ARGB1555 | 带宽减半 | 无 alpha 或色深下降 |
| 4 | 脏矩形局部刷新（只重画角色包围盒） | 2–5×（背景简单时） | 需维护脏区 |
| 5 | 条带渲染（内部 SRAM 画 800×64 条带 → DMA2D 搬运） | 改善 Cache 行为 | 复杂度上升 |
| 6 | 降渲染分辨率（如 640×384 后由 LTDC 放大） | 1.5× | 清晰度下降 |

---

## 9. 适配工作项

| ID | 工作项 | 方案 | 人日 | 风险 |
|---|---|---|---|---|
| W1 | 引入 spine-cpp | 直接引用 `D:\gitCode\spine_runtimes\spine-cpp`（同源已证实）或复制进 `thirdPartyComponents/`；记录 commit `405f4329` | 0.25 | 低（**已消除**）|
| W2 | MDK 工程改造 | AC5→**AC6**；`-std=c++1z -fno-exceptions -fno-rtti -include stdlib.h`；新增 C++ 源组；**禁用 Microlib**；分散加载加 SDRAM 段 | 1.0 | 中 |
| W3 | SDRAM + LTDC 驱动移植 | 从板级例程 `实验11`/`实验12` 导入 `sdram.c`/`ltdc.c` 到本项目 `Drivers/BSP`（当前为空） | 1.0 | 低 |
| W4 | 帧缓冲 + MPU/Cache | 双缓冲 + 换页（LTDC 中断）+ MPU 区域配置；DMA2D 清屏 | 1.5 | 中 |
| W5 | 资源管线 | 离线脚本：`.skel`+`.atlas`+`.png` → 头文件/二进制（ARGB8888）；实现 `spine_atlas_load_callback` + `SpineExtension` SDRAM 堆 | 2.0 | 中 |
| W6 | 渲染桥 | `RenderCommand` → TGX：索引拆三角、4 种 blend 算子、图集子区、顶点色映射 | 1.5 | 中 |
| W7 | **特性验证（IK/变形/裁剪）** | 用含 IK、网格变形、裁剪蒙版的测试动画逐项比对（与 Spine 编辑器预览截图对照） | 1.0 | 中（新增项）|
| W8 | 集成 Demo | DWT 基准、动画切换、串口/触摸控制 | 1.0 | 低 |
| W9 | 性能基准与优化 | §8.3 协议 + §8.5 阶梯 | 1.5 | 高（不确定）|
| **合计** | | | **≈ 10.75 人日** | |

---

## 10. 风险登记（V2 更新）

| 等级 | 风险 | 变化 | 缓解 |
|---|---|---|---|
| 🔴 高 | **渲染吞吐/帧率未知** | 仍在 | Phase 0 半天定量（§8.3），按决策表定尺寸与优化级别 |
| 🟡 中 | AC6.7 工具链老旧（C++17 草案级，无结构化绑定；后续引第三方库受限） | D4 已决定不变更 | 已验证可行；缓解手段：`-std=c++1z` + 规避写法 + `SPINE_NO_CPP_RT` |
| 🟡 中 | Cache/LTDC 一致性（花屏、撕裂） | 仍在 | 双缓冲 + non-cacheable 或每帧 clean；Phase 0 实测选型 |
| 🟡 中 | 资源管线细节（UV 归一化、图集页、色深对齐、PMA） | 仍在 | 离线转换脚本 + PC 端比对 + W7 逐项验证 |
| 🟢 低 | spine-cpp 缺件/版本漂移 | **已消除** | 同源同 commit 证实 |
| 🟢 低 | IK/变形/裁剪不支持 | **已消除** | 核心与 C API 均具备（§5） |
| 🟢 低 | 双色着色 darkColors 无对应 | 仍在 | 首期忽略；后续自写着色分支 |
| 🟢 低 | 动画尺寸未定 | 仍在 | 决策表（§8.4）支持反推"能播多大" |
| ⚪ — | 授权合规 | **已关闭** | 用户已有 Spine 4.3.x 正版授权 |

> 环境说明：本会话文件策略已放宽为完全访问，工作区子目录写权限问题不再存在，自动构建脚本可正常落盘。

---

## 11. 分阶段实施计划

| 阶段 | 内容 | 验收标准 | 预估 |
|---|---|---|---|
| **Phase 0** 基准先行 | 板级例程跑通 → SDRAM/LTDC 起来 → TGX 在真实帧缓冲画纹理三角形 → 按 §8.3 测 B1–B6 | 产出 **Mpx/s / ms·帧⁻¹ / 最大帧时间** 三张表；据此确认或调整尺寸与优化策略 | 0.5 天 |
| **Phase 1** 渲染骨架 | AC6 工程 + 双缓冲 + MPU/Cache + DMA2D + TGX 画旋转精灵 | 稳定 60 fps 精灵，无撕裂/花屏/颜色错 | 2 天 |
| **Phase 2** Spine 打通 | 引入 spine-cpp + 资源管线 + atlas 回调 + 渲染桥 | 播放真实 Spine 动画，颜色/透明度正确 | 3 天 |
| **Phase 3** 特性验证 | IK / 网格变形 / 裁剪蒙版 逐项与编辑器比对 | 三者视觉一致（截图对照），混合模式正确 | 1.5 天 |
| **Phase 4** 性能与健壮 | 按决策表启用优化阶梯；24 h 长跑；内存统计 | 达到定下的目标帧率；无泄漏、无漂移 | 2 天 |
| **Phase 5** 文档 | `docs/` 写接口与用法（规则 4）、示例工程、复现步骤 | 第三人可照文档复现 | 1 天 |

---

## 12. 仍需确认的少量事项

| # | 事项 | 说明 |
|---|---|---|
| R1 | **待播放动画的导出规格** | 需要你用 Spine 4.3.x 导出一份 `.skel` + `.atlas` + PNG（任意一个角色即可），Phase 2 才有素材；若能同时给出图集尺寸/骨骼数/动画数，内存估算可精确到 ±10% |
| R2 | **角色在屏幕上的目标占比** | 决定 §8.4 查表用哪一行；不确定也没关系，Phase 0 出数据后反推 |
| R3 | **是否需要触摸交互**（GT1151Q） | 若要，W8 增加 ~0.5 人日（I²C 触摸驱动 + 点击切换动画） |
| R4 | **是否要双色着色（darkColors）** | 首期默认忽略；若你的美术用到，需在 W6 增加自定义着色分支（+1 人日） |

---

## 附录 A：证据命令

```bash
AC=/d/MDK5/ARM/ARMCLANG/bin/armclang.exe
ARLINK=/d/MDK5/ARM/ARMCLANG/bin/armlink.exe

# 1) 版本配对（应输出 0 行）
diff -rq /d/gitCode/spine_runtimes/spine-c thirdPartyComponents/spine-c

# 2) C++17 支持
$AC --target=arm-arm-none-eabi -mcpu=cortex-m7 -std=c++17 -c x.cpp  # invalid value
$AC --target=arm-arm-none-eabi -mcpu=cortex-m7 -std=c++1z  -c x.cpp  # OK

# 3) 全量编译 + 链接体积（本仓库脚本）
bash DSH/middleware/ac6-probe/run_probe.sh /d/gitCode/spine_runtimes
#   → OK=227 FAIL=0
#   → Total RO 209,972 B (205 KB)  [默认移除未引用段]
#   → --no_remove 时 Total RO 390,252 B (381 KB)
```

## 附录 B：可复现探针（`DSH/middleware/ac6-probe/`）

| 文件 | 作用 |
|---|---|
| `README.md` | 复现步骤与实测数据 |
| `run_probe.sh` | 一键编译 227 文件 + 链接 + 体积统计 |
| `fix_stdlib.h` | 解决 `abs(int)` 二义（强制包含 `<stdlib.h>`） |
| `compat.h` / `spine_compat.c` | `strdup` 声明与实现（ARM C 库缺失） |
| `tgxprobe2.cpp` | TGX 纹理三角形（Spine 渲染关键路径）探针 |
| `linkmain.cpp` | Spine C-API 集成驱动探针（atlas 回调 + drawable + 渲染命令遍历） |

## 附录 C：本轮未做的事（明确边界）

- 未修改任何项目源文件（`save/` 备份因此未触发）；
- 未生成 MDK 工程配置（W2 属于 Phase 1，执行前会再次提交计划简报）；
- 未做真机基准（无硬件在环），故所有帧率数字均为**模型估算**，Phase 0 才产生实测值。
