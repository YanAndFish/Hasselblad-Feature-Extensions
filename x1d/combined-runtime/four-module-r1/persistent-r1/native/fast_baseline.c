/* 离线候选：逐字比较，压缩只减少基线体积，不采样、不替换为弱校验。
 * read_word 由验证环境提供。此文件不访问设备、不写内存、不发布钩子。
 * 正式接入前仍须解决版本确认、运行上下文、内存所有权和启动入口。
 */
#include <stdint.h>
#include <stddef.h>
struct FastRange {uint32_t address, words, offset, bytes;};
struct FastGuard {uint32_t address, mask, value;};
#include "../build/fast-start-research/fast_baseline_data.h"
typedef int (*FastRead)(void *, uint32_t, uint32_t *);
static uint32_t little_word(const unsigned char *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
int hbl_fast_check_memory(FastRead read_word, void *context) {
    if (!read_word) return 0;
    for (size_t i=0;i<sizeof(fast_ranges)/sizeof(fast_ranges[0]);++i) {
        const struct FastRange *r=&fast_ranges[i];
        if ((r->address & 3) || !r->words || r->words > (UINT32_MAX-r->address)/4 ||
            r->offset>sizeof(fast_bytes) || r->bytes>sizeof(fast_bytes)-r->offset) return 0;
        uint32_t position=r->offset, end=position+r->bytes, consumed=0;
        while (position<end) {
            unsigned token=fast_bytes[position++], count=(token&127)+1;
            unsigned data_bytes=(token&128)?4:4*count;
            if (count>r->words-consumed || data_bytes>end-position) return 0;
            for (unsigned j=0;j<count;++j) {
                uint32_t actual=0;
                uint32_t expected=little_word(fast_bytes+position+((token&128)?0:4*j));
                if (!read_word(context,r->address+4*consumed,&actual) || actual!=expected) return 0;
                ++consumed;
            }
            position+=data_bytes;
        }
        if (consumed!=r->words) return 0;
    }
    for (size_t i=0;i<sizeof(fast_guards)/sizeof(fast_guards[0]);++i) {
        uint32_t actual=0;
        if (!read_word(context,fast_guards[i].address,&actual) ||
            (actual&fast_guards[i].mask)!=fast_guards[i].value) return 0;
    }
    return 1;
}
