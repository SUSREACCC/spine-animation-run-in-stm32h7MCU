#!/bin/bash
# Flash Output/STM32H743.axf through ST-Link (OpenOCD) and verify.
# Usage: flash.sh [elf-or-hex path]
set -u
OCD_BIN="/d/OpenOCD/bin/openocd.exe"
OCD_SCRIPTS="D:/OpenOCD/share/openocd/scripts"
HERE="$(cd "$(dirname "$0")" && pwd)"
PROJ="$(cd "$HERE/../.." && pwd)"
IMAGE="${1:-D:/WorkSpace/MDK/H7spineRuntimeTest/Output/STM32H743.axf}"

if [ ! -f "$IMAGE" ] && [ ! -f "$(echo "$IMAGE" | sed 's#D:/#/d/#')" ]; then
    echo "image not found: $IMAGE"
    exit 1
fi

"$OCD_BIN" -s "$OCD_SCRIPTS" \
    -f interface/stlink.cfg \
    -f target/stm32h7x.cfg \
    -c "program {$IMAGE} verify reset exit" 2>&1 | grep -vE "^(Open On-Chip|xPack|For bug|	http)" | tail -25
