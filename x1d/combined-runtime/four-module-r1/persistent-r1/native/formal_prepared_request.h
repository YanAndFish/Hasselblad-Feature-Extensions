#ifndef HBL_FORMAL_PREPARED_REQUEST_H
#define HBL_FORMAL_PREPARED_REQUEST_H
#include "formal_netlink_wire.h"
/* 构建时校验 firmware-build.json 的源文件和 expectedHashesSha256。
 * 此表与正式芯片候选一起生成；不能用旧机械候选的固定哈希代替。 */
#ifdef HBL_EXTERNAL_RADIO_TABLES
#include <formal_flash_hashes.h>
#include <formal_flash_lut.h>
#else
#include "../build/formal-flash-candidate/formal_flash_hashes.h"
#include "../build/formal-flash-candidate/formal_flash_lut.h"
#endif

typedef struct {
    uint8_t bytes[128];
    size_t size;
    uint32_t sequence;
    unsigned ready;
} FormalPreparedRequest;
static inline int formal_selection_verified_config(unsigned index,uint32_t low,uint32_t high,
                                           uint32_t ready,uint32_t selected,unsigned channel,unsigned id) {
    uint32_t expected=0;
    return low<=0xffffu && high<=0xffffu && ready==1 && selected==index &&
           hbl_formal_wave_hash(&expected,index,channel,id,hbl_formal_lut) &&
           (low|(high<<16))==expected;
}
static inline int formal_selection_verified(unsigned index,uint32_t low,uint32_t high,
                                           uint32_t ready,uint32_t selected) {
    return index<HBL_FORMAL_WAVES && low<=0xffffu && high<=0xffffu &&
           ready==1 && selected==index && hbl_formal_hashes[index]!=0 &&
           (low|(high<<16))==hbl_formal_hashes[index];
}
static inline int formal_prepare_request(FormalPreparedRequest *p,uint16_t family,
                                        uint32_t previous,uint32_t port,uint32_t ifindex,
                                        unsigned selected) {
    if (!p) return 0;
    p->ready=0; p->size=0;
    if (previous==UINT32_MAX || selected!=HBL_FORMAL_FIRE_INDEX) return 0;
    p->sequence=previous+1;
    p->size=formal_nl_register_request(p->bytes,sizeof(p->bytes),family,p->sequence,port,ifindex,40);
    p->ready=p->size!=0;
    return p->ready;
}
static inline int formal_consume_request(FormalPreparedRequest *p,uint32_t previous) {
    if (!p || !p->ready || previous==UINT32_MAX || p->sequence!=previous+1) return 0;
    p->ready=0;
    return 1;
}
#endif
