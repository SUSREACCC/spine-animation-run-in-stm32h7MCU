#pragma once
// AC6(ARM Compiler 6.7) 的 libcxx <math.h> 只引入了 abs(float/double/long double)，
// 导致 TGX 中 abs(int) 调用产生二义。强制先包含 <stdlib.h> 可让 int 重载可见，
// 从而精确匹配。仅影响编译命令，不修改 TGX 源码。
#include <stdlib.h>
