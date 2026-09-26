#include "display_pixels.h"
#include "display_tables.h"

static uint8_t encoded(int64_t linear)
{
    linear = (linear + 524288) >> 20;
    if (linear <= 0) return 0;
    if (linear >= 1048576) return 255;
    uint32_t slot = (uint32_t)linear >> 8, part = (uint32_t)linear & 255;
    uint32_t v = srgb_encoded[slot] * (256 - part) + srgb_encoded[slot + 1] * part;
    /* 65535 / 255 = 257；常量除法由编译器展开。 */
    return (uint8_t)((v + 32896) / 65792);
}

int xj_display_bgra(uint8_t *p, uint32_t bytes, uint32_t width, uint32_t height, int adobe)
{
    if (!p || !width || !height || width > 8192 || height > 8192 ||
        (uint64_t)width * height * 4 != bytes || (adobe != 0 && adobe != 1)) return XJ_ARGUMENT;
    for (uint32_t i = 0; i < bytes; i += 4) {
        if (adobe) {
            uint32_t r = adobe_linear[p[i + 2]], g = adobe_linear[p[i + 1]], b = adobe_linear[p[i]];
            p[i + 2] = encoded((int64_t)adobe_to_srgb[0] * r + (int64_t)adobe_to_srgb[1] * g + (int64_t)adobe_to_srgb[2] * b);
            p[i + 1] = encoded((int64_t)adobe_to_srgb[3] * r + (int64_t)adobe_to_srgb[4] * g + (int64_t)adobe_to_srgb[5] * b);
            p[i] = encoded((int64_t)adobe_to_srgb[6] * r + (int64_t)adobe_to_srgb[7] * g + (int64_t)adobe_to_srgb[8] * b);
        }
        p[i + 3] = 255;
    }
    return XJ_OK;
}

static uint32_t div_u32(uint32_t value, uint32_t d)
{
    uint32_t quotient = 0, rem = 0;
    for (int bit = 31; bit >= 0; --bit) {
        rem = (rem << 1) | ((value >> bit) & 1);
        if (rem >= d) { rem -= d; quotient |= (uint32_t)1 << bit; }
    }
    return quotient;
}

static uint32_t destination(uint32_t i, uint32_t w, uint32_t h, uint32_t o, uint32_t reciprocal)
{
    uint32_t y = w == 1 ? i : (uint32_t)(((uint64_t)i * reciprocal) >> 32);
    if (y * w > i) --y;
    uint32_t x = i - y * w;
    switch (o) {
        case 2: return y * w + w - 1 - x;
        case 3: return w * h - 1 - i;
        case 4: return (h - 1 - y) * w + x;
        case 5: return x * h + y;
        case 6: return x * h + h - 1 - y;
        case 7: return (w - 1 - x) * h + h - 1 - y;
        case 8: return (w - 1 - x) * h + y;
        default: return i;
    }
}

int xj_orient_bgra(uint8_t *p, uint32_t bytes, uint32_t w, uint32_t h,
                    uint32_t o, uint8_t *visited, uint32_t capacity)
{
    if (!p || !w || !h || w > 8192 || h > 8192 || (uint64_t)w * h * 4 != bytes || o < 1 || o > 8)
        return XJ_ARGUMENT;
    if (o == 1) return XJ_OK;
    uint32_t n = w * h, need = (n + 7) >> 3;
    uint32_t reciprocal = div_u32(0xffffffffu, w) + 1;
    if (!visited || capacity < need) return XJ_CAPACITY;
    if (((uintptr_t)visited <= (uintptr_t)p && (uintptr_t)p - (uintptr_t)visited < capacity) ||
        ((uintptr_t)visited > (uintptr_t)p && (uintptr_t)visited - (uintptr_t)p < bytes)) return XJ_OVERLAP;
    for (uint32_t i = 0; i < need; ++i) visited[i] = 0;
    for (uint32_t i = 0; i < n; ++i) {
        if (visited[i >> 3] & (1u << (i & 7))) continue;
        uint8_t carry[4];
        for (uint32_t c = 0; c < 4; ++c) carry[c] = p[i * 4 + c];
        uint32_t current = i;
        do {
            uint32_t next = destination(current, w, h, o, reciprocal);
            for (uint32_t c = 0; c < 4; ++c) {
                uint8_t saved = p[next * 4 + c];
                p[next * 4 + c] = carry[c];
                carry[c] = saved;
            }
            visited[current >> 3] |= (uint8_t)(1u << (current & 7));
            current = next;
        } while (current != i);
    }
    return XJ_OK;
}
