#include "display_pixels.h"
#include "display_tables.h"
#include "display_fast_tables.h"

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
            const unsigned ri = p[i + 2], gi = p[i + 1], bi = p[i];
            unsigned red = fast_red[(ri << 8) | gi], green = fast_green[gi], blue = fast_blue[(gi << 8) | bi];
            if ((red | green | blue) & 256) {
                const uint32_t r = adobe_linear[ri], g = adobe_linear[gi], b = adobe_linear[bi];
                if (red == 256) red = encoded((int64_t)adobe_to_srgb[0] * r + (int64_t)adobe_to_srgb[1] * g + (int64_t)adobe_to_srgb[2] * b);
                if (green == 256) green = encoded((int64_t)adobe_to_srgb[3] * r + (int64_t)adobe_to_srgb[4] * g + (int64_t)adobe_to_srgb[5] * b);
                if (blue == 256) blue = encoded((int64_t)adobe_to_srgb[6] * r + (int64_t)adobe_to_srgb[7] * g + (int64_t)adobe_to_srgb[8] * b);
            }
            p[i + 2] = (uint8_t)red;
            p[i + 1] = (uint8_t)green;
            p[i] = (uint8_t)blue;
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

static void copy_bytes(uint8_t *to, const uint8_t *from, uint32_t bytes)
{ for (uint32_t i = 0; i < bytes; ++i) to[i] = from[i]; }

static void swap_pixel(uint8_t *a, uint8_t *b)
{
    for (unsigned c = 0; c < 4; ++c) {
        const uint8_t value = a[c]; a[c] = b[c]; b[c] = value;
    }
}

/* 整图布局先按行带转换为连续小块，再排列小块，最后恢复逐行布局。
 * 原地循环的随机访问由一个像素扩大到最多 16x16 像素；没有第二张整图。
 * 奇数/小尺寸仍使用原逐像素循环，不增加旧 scratch 预算。 */
static uint32_t tile_side(uint32_t w, uint32_t h)
{
    for (uint32_t shift = 4; shift >= 1; --shift) {
        const uint32_t side = 1u << shift;
        if ((w & (side - 1)) || (h & (side - 1))) continue;
        const uint32_t tiles = (w >> shift) * (h >> shift);
        const uint32_t need = (w > h ? w : h) * side * 4 + ((tiles + 7) >> 3);
        if (need <= ((w * h + 7) >> 3)) return side;
    }
    return 0;
}

static uint32_t tile_shift(uint32_t side)
{ return side == 16 ? 4 : side == 8 ? 3 : side == 4 ? 2 : 1; }

uint32_t xj_orient_scratch_bytes(uint32_t w, uint32_t h, uint32_t o)
{
    if (!w || !h || w > 8192 || h > 8192 || o < 1 || o > 8) return 0;
    if (o <= 4) return 0;
    const uint32_t side = tile_side(w, h);
    const uint32_t shift = tile_shift(side);
    return side ? (w > h ? w : h) * side * 4 + ((((w >> shift) * (h >> shift)) + 7) >> 3)
                : ((w * h + 7) >> 3);
}

static void tile_layout(uint8_t *p, uint32_t w, uint32_t h, uint32_t side, uint8_t *scratch, int pack)
{
    const uint32_t band = w * side * 4, row = side * 4, block = side * row;
    const uint32_t columns = w >> tile_shift(side);
    for (uint32_t y = 0; y < h; y += side) {
        uint8_t *base = p + y * w * 4;
        copy_bytes(scratch, base, band);
        for (uint32_t x = 0; x < columns; ++x) {
            for (uint32_t r = 0; r < side; ++r) {
                const uint32_t linear = (r * w + x * side) * 4;
                const uint32_t tiled = x * block + r * row;
                copy_bytes(base + (pack ? tiled : linear), scratch + (pack ? linear : tiled), row);
            }
        }
    }
}

static void orient_tile(uint8_t *to, const uint8_t *from, uint32_t side, uint32_t o)
{
    for (uint32_t y = 0; y < side; ++y) {
        for (uint32_t x = 0; x < side; ++x) {
            const uint32_t dx = (o == 6 || o == 7) ? side - 1 - y : y;
            const uint32_t dy = (o == 7 || o == 8) ? side - 1 - x : x;
            copy_bytes(to + (dy * side + dx) * 4, from + (y * side + x) * 4, 4);
        }
    }
}

static void tiled_orientation(uint8_t *p, uint32_t w, uint32_t h, uint32_t o, uint32_t side, uint8_t *scratch)
{
    const uint32_t shift = tile_shift(side), columns = w >> shift, rows = h >> shift, n = columns * rows;
    const uint32_t block = side * side * 4;
    uint8_t *seen = scratch + (w > h ? w : h) * side * 4;
    uint8_t carry[16 * 16 * 4], saved[16 * 16 * 4];
    tile_layout(p, w, h, side, scratch, 1);
    for (uint32_t i = 0; i < (n + 7) / 8; ++i) seen[i] = 0;
    const uint32_t reciprocal = div_u32(0xffffffffu, columns) + 1;
    for (uint32_t i = 0; i < n; ++i) {
        if (seen[i >> 3] & (1u << (i & 7))) continue;
        copy_bytes(carry, p + i * block, block);
        uint32_t current = i;
        do {
            const uint32_t next = destination(current, columns, rows, o, reciprocal);
            copy_bytes(saved, p + next * block, block);
            orient_tile(p + next * block, carry, side, o);
            copy_bytes(carry, saved, block);
            seen[current >> 3] |= (uint8_t)(1u << (current & 7));
            current = next;
        } while (current != i);
    }
    tile_layout(p, h, w, side, scratch, 0);
}

int xj_orient_bgra(uint8_t *p, uint32_t bytes, uint32_t w, uint32_t h,
                    uint32_t o, uint8_t *visited, uint32_t capacity)
{
    if (!p || !w || !h || w > 8192 || h > 8192 || (uint64_t)w * h * 4 != bytes || o < 1 || o > 8)
        return XJ_ARGUMENT;
    if (o == 1) return XJ_OK;
    if (o == 2) {
        for (uint32_t y = 0; y < h; ++y)
            for (uint32_t x = 0; x < w / 2; ++x)
                swap_pixel(p + (y * w + x) * 4, p + (y * w + w - 1 - x) * 4);
        return XJ_OK;
    }
    if (o == 3) {
        for (uint32_t i = 0; i < w * h / 2; ++i) swap_pixel(p + i * 4, p + (w * h - 1 - i) * 4);
        return XJ_OK;
    }
    if (o == 4) {
        for (uint32_t y = 0; y < h / 2; ++y)
            for (uint32_t x = 0; x < w; ++x)
                swap_pixel(p + (y * w + x) * 4, p + ((h - 1 - y) * w + x) * 4);
        return XJ_OK;
    }
    uint32_t n = w * h, need = xj_orient_scratch_bytes(w, h, o);
    if (!visited || capacity < need) return XJ_CAPACITY;
    if (((uintptr_t)visited <= (uintptr_t)p && (uintptr_t)p - (uintptr_t)visited < capacity) ||
        ((uintptr_t)visited > (uintptr_t)p && (uintptr_t)visited - (uintptr_t)p < bytes)) return XJ_OVERLAP;
    const uint32_t side = tile_side(w, h);
    if (side) {
        tiled_orientation(p, w, h, o, side, visited);
        return XJ_OK;
    }
    const uint32_t reciprocal = div_u32(0xffffffffu, w) + 1;
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
