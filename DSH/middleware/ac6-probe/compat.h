#pragma once
// ARM C 库未提供 POSIX strdup，而 spine-c/src/extensions.cpp 使用它。
// 这里只做声明，实现见 spine_compat.c。
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

char *strdup(const char *s);

#ifdef __cplusplus
}
#endif
