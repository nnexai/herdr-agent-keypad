#pragma once
#include <cstdint>
inline uint32_t micros() { static uint32_t now = 0; return now += 100; }
