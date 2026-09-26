#ifndef HBL_FARM_REPLY_WIRE_H
#define HBL_FARM_REPLY_WIRE_H
#include <stddef.h>
#include <stdint.h>

/* 原厂 AppsMessage 的成功 F5 回复：FARM(1) -> iMX(5)。 */
static inline int hbl_parse_farm_reply(const uint8_t *bytes, size_t length,
                                      uint32_t *value) {
    if (!bytes || !value || length != 9 || bytes[0] != 0xf5 || bytes[1] != 0 ||
        bytes[2] != 1 || bytes[3] != 5 || bytes[8] != 0) return 0;
    *value = (uint32_t)bytes[4] | ((uint32_t)bytes[5] << 8) |
             ((uint32_t)bytes[6] << 16) | ((uint32_t)bytes[7] << 24);
    return 1;
}

static inline void hbl_reply_put32(uint8_t *out, uint32_t value) {
    for (unsigned i = 0; i != 4; ++i) out[i] = (uint8_t)(value >> (8 * i));
}

/* 自有进程间数据，时间仅表示 Linux 分发之后，不是 FARM 感光时间。 */
static inline void hbl_pack_farm_reply(uint8_t out[24], uint32_t sequence,
                                      uint32_t value, uint64_t receive_ns) {
    hbl_reply_put32(out, 0x31505246u); /* FRP1 */
    hbl_reply_put32(out + 4, 1);
    hbl_reply_put32(out + 8, sequence);
    hbl_reply_put32(out + 12, value);
    hbl_reply_put32(out + 16, (uint32_t)receive_ns);
    hbl_reply_put32(out + 20, (uint32_t)(receive_ns >> 32));
}
#endif
