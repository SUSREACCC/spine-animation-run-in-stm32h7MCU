#!/usr/bin/env python3
"""Enable FreeRTOS in the copied project (H7spineRuntimeTest_RTOS).

  plat_cfg.h        : PLAT_USE_RTOS=1, PLAT_ENABLE_MEM_LOCK=1
  plat_init()       : SysTick priority -> lowest (FreeRTOS requirement)
  stm32h7xx_it.c    : SysTick_Handler also calls xPortSysTickHandler()
  FreeRTOSConfig.h  : bigger heap
  uvprojx           : FreeRTOS group + 2 include paths
  rtos_demo.c       : render task + heartbeat task, started from selftest

Run from the RTOS project root:  python DSH/middleware/enable_rtos.py
"""
import io
import re

CFG = "User/plat/plat_cfg.h"
PLAT = "User/plat/plat_stm32h7.c"
IT = "User/stm32h7xx_it.c"
FRCFG = "User/FreeRTOSConfig.h"
PROJ = "Projects/MDK-ARM/STM32H743.uvprojx"
SELFTEST = "User/selftest.c"

FREERTOS_C = [
    "croutine.c", "event_groups.c", "list.c", "queue.c",
    "stream_buffer.c", "tasks.c", "timers.c",
]


def patch_cfg():
    s = io.open(CFG, encoding="utf-8").read()
    s = s.replace("#define PLAT_USE_RTOS           0", "#define PLAT_USE_RTOS           1")
    s = s.replace("#define PLAT_ENABLE_MEM_LOCK    0", "#define PLAT_ENABLE_MEM_LOCK    1")
    io.open(CFG, "w", encoding="utf-8", newline="").write(s)
    print("plat_cfg: RTOS enabled, mem lock enabled")


def patch_systick_priority():
    s = io.open(PLAT, encoding="utf-8").read()

    if "SysTick_IRQn" in s:
        print("plat: systick priority already set")
        return

    old = """void plat_init(void)
{
#if PLAT_USE_RTOS"""
    new = """void plat_init(void)
{
#if PLAT_USE_RTOS
    /* FreeRTOS 要求 SysTick 处于最低优先级（HAL_InitTick 会把它设成最高） */
    HAL_NVIC_SetPriority(SysTick_IRQn, 15, 0);
"""
    assert old in s
    s = s.replace(old, new, 1)
    io.open(PLAT, "w", encoding="utf-8", newline="").write(s)
    print("plat: SysTick priority -> lowest")


def patch_systick_handler():
    s = io.open(IT, encoding="utf-8").read()

    if "xPortSysTickHandler" in s:
        print("it.c: already patched")
        return

    old = """void SysTick_Handler(void)
{"""
    new = """#if PLAT_USE_RTOS
extern void xPortSysTickHandler(void);
#endif

void SysTick_Handler(void)
{"""
    assert old in s
    s = s.replace(old, new, 1)

    # 在 HAL_IncTick 之后调用 FreeRTOS 的 tick
    old2 = """  HAL_IncTick();"""
    new2 = """  HAL_IncTick();

#if PLAT_USE_RTOS
  xPortSysTickHandler();
#endif"""
    assert old2 in s
    s = s.replace(old2, new2, 1)

    # 需要 plat_cfg.h
    if 'plat/plat_cfg.h' not in s:
        s = s.replace('#include "stm32h7xx_it.h"', '#include "stm32h7xx_it.h"\n#include "plat/plat_cfg.h"', 1)

    io.open(IT, "w", encoding="utf-8", newline="").write(s)
    print("it.c: SysTick_Handler now feeds both HAL and FreeRTOS")


def patch_heap_size():
    s = io.open(FRCFG, encoding="utf-8").read()
    s = re.sub(r"#define configTOTAL_HEAP_SIZE\s+\(\(size_t\)\(46 \* 1024\)\)",
               "#define configTOTAL_HEAP_SIZE                 ((size_t)(64 * 1024))", s)
    s = re.sub(r"#define configTOTAL_HEAP_SIZE\s+\(\(size_t\)\([0-9]+ \* 1024\)\)",
               "#define configTOTAL_HEAP_SIZE                 ((size_t)(64 * 1024))", s)
    io.open(FRCFG, "w", encoding="utf-8", newline="").write(s)
    print("FreeRTOSConfig: heap -> 64 KB")


def make_file_block(name, path):
    return """            <File>
              <FileName>%s</FileName>
              <FileType>1</FileType>
              <FilePath>%s</FilePath>
            </File>
""" % (name, path)


def patch_project():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()

    if "FreeRTOS" in s and "tasks.c" in s:
        print("uvprojx: FreeRTOS already present")
        return

    # 1) include paths（追加到第一个非空的 IncludePath）
    add_inc = "..\\..\\Middlewares\\FreeRTOS\\include;..\\..\\Middlewares\\FreeRTOS\\portable\\RVDS\\ARM_CM7\\r0p1;"
    m = re.search(r"<IncludePath>(\.\.\\\.\.\\Drivers\\CMSIS[^<]*)</IncludePath>", s)
    if not m:
        raise SystemExit("include path entry not found")
    s = s[:m.start(1)] + m.group(1) + add_inc + s[m.end(1):]

    # 2) 新组
    files = ""
    for c in FREERTOS_C:
        files += make_file_block(c, "..\\..\\Middlewares\\FreeRTOS\\" + c)
    files += make_file_block("port.c", "..\\..\\Middlewares\\FreeRTOS\\portable\\RVDS\\ARM_CM7\\r0p1\\port.c")
    files += make_file_block("heap_4.c", "..\\..\\Middlewares\\FreeRTOS\\portable\\MemMang\\heap_4.c")

    group = """        <Group>
          <GroupName>Middlewares/FreeRTOS</GroupName>
%s        </Group>
""" % files

    # 插到 </Groups> 之前
    idx = s.rfind("</Groups>")
    if idx < 0:
        raise SystemExit("</Groups> not found")
    s = s[:idx] + group + s[idx:]

    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)
    print("uvprojx: FreeRTOS group + include paths added")


DEMO = r'''
/*----------------------------------------------------------------- FreeRTOS 演示 */

#if PLAT_USE_RTOS

#include "FreeRTOS.h"
#include "task.h"
#include "plat/plat.h"
#include "spine_api.h"

static void rtos_render_task(void *arg)
{
    const char *SKEL = "/spine/celestial-circus-pro.skel";
    const char *ATLAS = "/spine/celestial-circus-pro.atlas";

    (void)arg;

    spine_asset_t *asset = spine_asset_load(SKEL, ATLAS);

    if (asset == 0)
    {
        printf("[RTOS] asset load failed\r\n");
        vTaskDelete(NULL);
        return;
    }

    spine_instance_t *hero = spine_instance_create(asset);
    spine_instance_t *enemy = spine_instance_create(asset);

    spine_instance_play(hero, "swing", 1, 0);
    spine_instance_play(enemy, "wing-flap", 1, 0);

    float x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    spine_instance_get_bounds(hero, &x0, &y0, &x1, &y1);

    float s = 220.0f / (y1 - y0);
    float cx = (x0 + x1) * 0.5f;
    float cy = (y0 + y1) * 0.5f;

    spine_instance_set_scale(hero, s);
    spine_instance_set_position(hero, 210.0f - cx * s, 250.0f - cy * s);
    spine_instance_set_scale(enemy, s);
    spine_instance_set_position(enemy, 590.0f - cx * s, 250.0f - cy * s);
    spine_instance_set_tint(enemy, 0xFFB0D0FFu);

    printf("[RTOS] render task started, scale=%.3f\r\n", (double)s);

    uint32_t frames = 0;
    uint32_t t0 = plat_now_ms();
    const float dt = 1.0f / 60.0f;

    for (;;)
    {
        spine_instance_update(hero, dt);
        spine_instance_update(enemy, dt);

        spine_draw_begin(2);
        spine_instance_draw(hero);
        spine_instance_draw(enemy);
        spine_draw_end();

        frames++;

        if ((frames % 60u) == 0u)
        {
            uint32_t el = plat_now_ms() - t0;

            if (el == 0) { el = 1; }

            printf("[RTOS] render: %lu frames, %.2f ms/frame, free heap %u\r\n",
                   (unsigned long)frames, (double)((float)el / (float)frames),
                   (unsigned)xPortGetFreeHeapSize());

            frames = 0;
            t0 = plat_now_ms();
        }

        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

static void rtos_beat_task(void *arg)
{
    uint32_t n = 0;

    (void)arg;

    for (;;)
    {
        printf("[RTOS] beat %lu\r\n", (unsigned long)n++);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

void rtos_demo_start(void)
{
    plat_init();

    printf("[RTOS] starting scheduler, free heap=%u\r\n", (unsigned)xPortGetFreeHeapSize());

    xTaskCreate(rtos_render_task, "render", 2048, NULL, 3, NULL);
    xTaskCreate(rtos_beat_task, "beat", 512, NULL, 2, NULL);

    vTaskStartScheduler();

    printf("[RTOS] scheduler returned (should never happen)\r\n");

    for (;;)
    {
    }
}

#endif /* PLAT_USE_RTOS */
'''


def patch_selftest():
    s = io.open(SELFTEST, encoding="utf-8").read()

    if "rtos_demo_start" in s:
        print("selftest: already wired")
        return

    # 前置声明 + 调用
    s = s.replace('#include "plat/plat.h"', '#include "plat/plat.h"\n\n#if PLAT_USE_RTOS\nvoid rtos_demo_start(void);\n#endif', 1)

    anchor = '    printf("heartbeat start'
    i = s.find(anchor)
    assert i > 0, "heartbeat anchor missing"

    s = s[:i] + "#if PLAT_USE_RTOS\n    rtos_demo_start();      /* 不返回：调度器接管 */\n#endif\n\n" + s[i:]
    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
    print("selftest: rtos_demo_start() wired")


def write_demo():
    s = io.open(SELFTEST, encoding="utf-8").read()

    if "static void rtos_render_task" in s:
        print("demo already present")
        return

    # 插到 selftest_run 之前（文件作用域）
    idx = s.find("void selftest_run(void)")
    assert idx > 0
    s = s[:idx] + DEMO.strip() + "\n\n" + s[idx:]
    io.open(SELFTEST, "w", encoding="utf-8", newline="").write(s)
    print("demo written into selftest.c")


def copy_os_adapter():
    src = "User/plat/plat_os_freertos.c.template"
    dst = "User/plat/plat_os_freertos.c"

    s = io.open(src, encoding="utf-8").read()
    io.open(dst, "w", encoding="utf-8", newline="").write(s)
    print("plat_os_freertos.c created from template")


def add_adapter_to_project():
    s = io.open(PROJ, encoding="utf-8", errors="ignore").read()

    if "plat_os_freertos.c" in s:
        print("uvprojx: adapter already present")
        return

    block = """            <File>
              <FileName>plat_os_freertos.c</FileName>
              <FileType>1</FileType>
              <FilePath>..\\..\\User\\plat\\plat_os_freertos.c</FilePath>
            </File>
"""
    # 放到 plat_stm32h7.c 之后
    m = re.search(r"[ \t]*<File>\s*<FileName>plat_stm32h7\.c</FileName>.*?</File>", s, re.S)
    if not m:
        raise SystemExit("plat_stm32h7.c entry not found")
    s = s[:m.end()] + "\n" + block + s[m.end():]
    io.open(PROJ, "w", encoding="utf-8", newline="").write(s)
    print("uvprojx: plat_os_freertos.c added")


def main():
    copy_os_adapter()
    patch_cfg()
    patch_systick_priority()
    patch_systick_handler()
    patch_heap_size()
    patch_project()
    add_adapter_to_project()
    write_demo()
    patch_selftest()


if __name__ == "__main__":
    main()
