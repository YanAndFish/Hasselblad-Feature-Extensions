#include "../native/farm_reply_wire.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void) {
    uint8_t valid[10] = {0xf5, 0, 1, 5, 0x78, 0x56, 0x34, 0x12, 0, 0};
    uint32_t value = 0;
    assert(hbl_parse_farm_reply(valid, 9, &value) && value == 0x12345678);
    for (size_t size = 0; size <= 10; ++size) {
        if (size == 9) continue;
        value = 0xfeedface;
        assert(!hbl_parse_farm_reply(valid, size, &value) && value == 0xfeedface);
    }
    const size_t guarded[] = {0, 1, 2, 3, 8};
    for (size_t field = 0; field < sizeof(guarded) / sizeof(guarded[0]); ++field) {
        uint8_t changed[9];
        memcpy(changed, valid, sizeof(changed));
        changed[guarded[field]] ^= 1;
        value = 0xfeedface;
        assert(!hbl_parse_farm_reply(changed, sizeof(changed), &value));
        assert(value == 0xfeedface);
    }
    assert(!hbl_parse_farm_reply(NULL, 9, &value));
    assert(!hbl_parse_farm_reply(valid, 9, NULL));
    uint8_t wrapped[26];
    memset(wrapped, 0xa5, sizeof(wrapped));
    hbl_pack_farm_reply(wrapped + 1, 17, 0x12345678, UINT64_C(0x0102030405060708));
    const uint8_t expected[24] = {
        'F','R','P','1', 1,0,0,0, 17,0,0,0, 0x78,0x56,0x34,0x12,
        8,7,6,5,4,3,2,1
    };
    assert(wrapped[0] == 0xa5 && wrapped[25] == 0xa5);
    assert(!memcmp(wrapped + 1, expected, sizeof(expected)));
    puts("{\"success_reply\":true,\"invalid_lengths\":10,\"header_status_rejections\":5,\"null_rejections\":2,\"packet_and_canary\":true}");
    return 0;
}
