# AC6.7 移植探针（spine-c 4.3 + spine-cpp 4.3 + TGX 1.1.4）

本目录是 `DSH/spine-porting-feasibility.md` 的证据与复现脚本。
**不修改任何第三方源码**：所有兼容问题都用 `-include` 注入的最小 shim 解决。

## 环境

| 项 | 值 |
|---|---|
| 编译器 | `D:\MDK5\ARM\ARMCLANG\bin\armclang.exe`（ARM Compiler **6.7** / MDK Plus 5.24）|
| 链接器 | `D:\MDK5\ARM\ARMCLANG\bin\armlink.exe` |
| 目标 | `--target=arm-arm-none-eabi -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard` |
| 语言 | `-std=c++1z`（**注意：AC6.7 不认 `-std=c++17`**）、`-fno-exceptions -fno-rtti` |
| spine 源 | 本地 `thirdPartyComponents/spine-c` + `D:\gitCode\spine_runtimes\spine-cpp`（同源，见下） |

## 版本配对（已证实）

```bash
diff -rq /d/gitCode/spine_runtimes/spine-c thirdPartyComponents/spine-c   # 输出为空
```

⇒ 工程内 `spine-c` 与本地 git 检出（branch `4.3` @ `405f4329`）**逐字节一致**，`spine-cpp` 直接同源引用即可。

## 已知的两个兼容点

1. **`abs(int)` 二义**：AC6 的 libcxx `<math.h>` 只引入 `abs(float/double/long double)`，
   TGX 里的 `abs(int)` 调用歧义。→ 编译 TGX 的 TU 加 `-include fix_stdlib.h`
   （内容仅 `#include <stdlib.h>`）。**不需要改 TGX 源码。**
2. **`strdup` 未声明**：ARM C 库不提供 POSIX `strdup`，`spine-c/src/extensions.cpp` 用到。
   → `-include compat.h` 声明 + 链接 `spine_compat.c` 提供 10 行实现。

## 复现

```bash
bash DSH/middleware/ac6-probe/run_probe.sh /d/gitCode/spine_runtimes
```

## 实测结果（V2，2026-11-14，使用本地 spine-cpp）

| 项 | 结果 |
|---|---|
| 编译源文件数 | **227**（spine-cpp 88 + spine-c 生成层 134 + extensions 1 + TGX/兼容层 4）|
| 编译结果 | **0 error / 0 fail** |
| 链接（默认移除未引用段，`.skel` 路径） | **Total RO 209,972 B（205 KB）**；RW 88 B；ZI ≈ 2.5 KB |
| 链接（`--no_remove`，强制全保留） | **Total RO 390,252 B（381 KB）** |
| TGX 纹理三角形单 TU | Code **3,288 B** |
| 最大目标文件 | `SkeletonJson.o` 52,984 B（走 `.skel` 时不会被链接进来）|
| | `SkeletonBinary.o` 44,748 B |
| | `SkeletonClipping.o` 9,968 B / `AnimationState.o` 9,718 B / `Atlas.o` 7,952 B |

> 注意：`armlink` **默认移除未被引用的输入段**。因此“只解码 `.skel`”的配置是 **205 KB**，
> 强制全保留是 **381 KB**。报告采用这两个数；早前的 295 KB 为中间态数据，已废弃。

## 结构体尺寸（ARM 32-bit，用于内存估算）

| 类型 | 字节 | 类型 | 字节 |
|---|---|---|---|
| `BoneData` | 160 | `Skeleton` | 212 |
| `SlotData` | 128 | `SkeletonData` | 224 |
| `RegionAttachment` | 112 | `AtlasRegion` | 160 |
| `MeshAttachment` | 188 | `Animation` | 104 |
| `ClippingAttachment` | 112 | `TrackEntry` | 188 |
| `IkConstraint` | 92 | `EventData` | 80 |
| `Skin` | 92 | `AnimationState` | 132 |

## 文件说明

| 文件 | 作用 |
|---|---|
| `run_probe.sh` | 一键编译全部 spine 源 + TGX 关键路径 + 链接统计 |
| `fix_stdlib.h` | 解决 `abs(int)` 二义的强制包含头 |
| `compat.h` | `strdup` 声明（供 C++ 侧包含） |
| `spine_compat.c` | `strdup` 的 C 实现（ARM C 库缺失） |
| `tgxprobe2.cpp` | TGX 纹理三角形（spine 渲染关键路径）探针 |
| `linkmain.cpp` | spine C-API 集成驱动探针（atlas 回调 + drawable + 渲染命令遍历）|
