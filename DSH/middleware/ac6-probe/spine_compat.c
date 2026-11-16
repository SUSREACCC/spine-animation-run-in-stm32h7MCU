/* ARM C 库未提供 POSIX strdup 的最小实现（约 10 行）。
 * 供 spine-c/src/extensions.cpp 使用；仅在目标平台需要时链接。 */
#include <string.h>
#include <stdlib.h>

char *strdup(const char *s)
{
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);
    if (p) {
        memcpy(p, s, n);
    }
    return p;
}
