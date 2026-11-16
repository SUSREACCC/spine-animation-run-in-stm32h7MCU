#!/bin/bash
# STM32H743 × Spine 4.3 × TGX 1.1.4 —— AC6(armclang) 移植探针
# 用法: run_probe.sh [spine-runtimes 根目录]  (默认 /tmp/sp43/spine-runtimes-4.3)
# 作用: 编译 spine-cpp + spine-c 全部源文件与 TGX 关键路径, 链接成镜像并统计体积。
# 注意: 不修改任何第三方源码; 兼容问题全部由 -include 注入的 shim 解决。

set -u
PROBE_DIR="$(cd "$(dirname "$0")" && pwd)"
SPINE_ROOT="${1:-/tmp/sp43/spine-runtimes-4.3}"
AC="/d/MDK5/ARM/ARMCLANG/bin/armclang.exe"
ARLINK="/d/MDK5/ARM/ARMCLANG/bin/armlink.exe"
FROMELF="/d/MDK5/ARM/ARMCLANG/bin/fromelf.exe"
TGX_SRC="${PROBE_DIR}/../../../thirdPartyComponents/tgx-main/src"
OUT="/tmp/spine-probe-out"

[ -x "$AC" ] || { echo "找不到 armclang: $AC"; exit 1; }
[ -d "$SPINE_ROOT/spine-cpp" ] || { echo "找不到 spine-cpp: $SPINE_ROOT/spine-cpp"; exit 1; }

ARCH="--target=arm-arm-none-eabi -mcpu=cortex-m7 -mfpu=fpv5-d16 -mfloat-abi=hard"
BASE="$ARCH -std=c++1z -O2 -fno-exceptions -fno-rtti -DNDEBUG"
SPINE_INC="-I$SPINE_ROOT/spine-cpp/include -I$SPINE_ROOT/spine-c/include -I$SPINE_ROOT/spine-c/src"

rm -rf "$OUT"; mkdir -p "$OUT/cpp" "$OUT/csrc" "$OUT/misc"
ok=0; fail=0

compile() { # src out extra_flags...
  local src="$1"; shift
  local out="$1"; shift
  if "$AC" $BASE "$@" -c "$src" -o "$out" 2> "${out%.o}.err"; then
    ok=$((ok+1))
  else
    fail=$((fail+1)); echo "FAIL: $src"; head -6 "${out%.o}.err"
  fi
}

echo "== 1/4 spine-cpp =="
for f in "$SPINE_ROOT"/spine-cpp/src/spine/*.cpp; do
  compile "$f" "$OUT/cpp/$(basename "${f%.cpp}").o" -I"$SPINE_ROOT/spine-cpp/include" -I"$SPINE_ROOT/spine-cpp/src"
done

echo "== 2/4 spine-c 生成层 =="
for f in "$SPINE_ROOT"/spine-c/src/generated/*.cpp; do
  compile "$f" "$OUT/csrc/$(basename "${f%.cpp}").o" $SPINE_INC
done

echo "== 3/4 extensions + compat + TGX + 集成驱动 =="
compile "$SPINE_ROOT/spine-c/src/extensions.cpp" "$OUT/misc/extensions.o" -include "$PROBE_DIR/compat.h" $SPINE_INC
compile "$PROBE_DIR/spine_compat.c"               "$OUT/misc/spine_compat.o" -std=c99
compile "$PROBE_DIR/tgxprobe2.cpp"                "$OUT/misc/tgxprobe2.o" -DF_CPU=480000000 -include "$PROBE_DIR/fix_stdlib.h" -I"$TGX_SRC"
compile "$PROBE_DIR/linkmain.cpp"                 "$OUT/misc/linkmain.o"  -include "$PROBE_DIR/fix_stdlib.h" -I"$TGX_SRC" $SPINE_INC
compile "$TGX_SRC/Color.cpp"                      "$OUT/misc/tgx_color.o" -DF_CPU=480000000 -include "$PROBE_DIR/fix_stdlib.h" -I"$TGX_SRC"

echo "编译结果: OK=$ok FAIL=$fail"

echo "== 4/4 链接与体积 =="
"$ARLINK" --cpu=Cortex-M7.fp.dp --no_startup --entry=app --info=sizes --info=totals \
  -o "$OUT/test.axf" "$OUT"/misc/*.o "$OUT"/cpp/*.o "$OUT"/csrc/*.o 2>&1 | tail -18

echo
echo "TGX 纹理三角形体积:"
"$FROMELF" --text -z "$OUT/misc/tgxprobe2.o" 2>/dev/null | grep -E '^\s+[0-9]+' | head -2
