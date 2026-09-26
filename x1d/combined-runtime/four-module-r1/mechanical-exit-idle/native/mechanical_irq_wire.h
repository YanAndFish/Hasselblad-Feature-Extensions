#ifndef HBL_MECHANICAL_IRQ_WIRE_H
#define HBL_MECHANICAL_IRQ_WIRE_H
#include <stddef.h>
#include <stdint.h>
#define HBL_MECH_MAGIC UINT32_C(0x31534d47)
#define HBL_MECH_IPC_MAGIC UINT32_C(0x314c4d47)
#define HBL_MECH_SOCKET "/tmp/hbl-wireless-flash/mechanical-sync.sock"
#define HBL_MECH_CLOCK 4u
#define HBL_MECH_DONE 0x8000u
#define HBL_MECH_SOURCES 7u /* 保留既有来源编号 2/3，不把界面下标当协议编号。 */
#define HBL_MECH_EVENT_MASK 0x0cu
struct HblMechanicalSync {
    uint32_t magic,version,trial,clear_flags,cleared_status,sync_status;
    uint32_t timer_low,timer_high,timer_control,mode,source;
};
static inline uint32_t hbl_mech_u32(const uint8_t *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
static inline void hbl_mech_put32(uint8_t *p,uint32_t v) {
    for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(v>>(i*8));
}
/* version=2 仅由新 IRQ 处理器生成。事件位来自中断编号；sync_status 是
 * ISR 到达时另读的状态，可能已变化，不把它伪装成 FPGA 边沿锁存值。
 * version=1 的旧状态轮询消息明确拒绝。
 */
static inline int hbl_mech_fields_valid(const struct HblMechanicalSync *s) {
    if (!s || s->magic!=HBL_MECH_MAGIC || s->version!=2 || !s->trial ||
        s->mode>1 || s->source!=3 || (s->clear_flags&~0x8c04u)) return 0;
    if ((s->clear_flags&HBL_MECH_CLOCK) && !(s->timer_control&1)) return 0;
    if ((s->clear_flags&HBL_MECH_DONE) && (s->clear_flags&0x0c00)) return 0;
    return 1;
}
static inline int hbl_mech_confirmed(const struct HblMechanicalSync *s,unsigned source) {
    return hbl_mech_fields_valid(s) && (source==2 || source==3) &&
           (s->clear_flags&HBL_MECH_CLOCK) && (s->clear_flags&(1u<<(source+8)));
}
static inline int hbl_parse_mech_message(const uint8_t *p,size_t n,struct HblMechanicalSync *s) {
    if (!p || !s || n!=260 || hbl_mech_u32(p)!=UINT32_C(0x05010009)) return 0;
    uint32_t *fields=(uint32_t *)s;
    for (unsigned i=0;i<11;++i) fields[i]=hbl_mech_u32(p+4+4*i);
    if (!hbl_mech_fields_valid(s)) return 0;
    for (size_t i=48;i<n;++i) if (p[i]) return 0;
    return 1;
}
static inline void hbl_pack_mech_ipc(uint8_t p[64],uint32_t epoch,const struct HblMechanicalSync *s,uint64_t ns) {
    hbl_mech_put32(p,HBL_MECH_IPC_MAGIC); hbl_mech_put32(p+4,2); hbl_mech_put32(p+8,epoch);
    const uint32_t *fields=(const uint32_t *)s;
    for (unsigned i=0;i<11;++i) hbl_mech_put32(p+12+4*i,fields[i]);
    hbl_mech_put32(p+56,(uint32_t)ns); hbl_mech_put32(p+60,(uint32_t)(ns>>32));
}
static inline int hbl_parse_mech_ipc(const uint8_t *p,size_t n,uint32_t *epoch,struct HblMechanicalSync *s,uint64_t *ns) {
    if (!p || !epoch || !s || !ns || n!=64 || hbl_mech_u32(p)!=HBL_MECH_IPC_MAGIC ||
        hbl_mech_u32(p+4)!=2 || !hbl_mech_u32(p+8)) return 0;
    uint32_t *fields=(uint32_t *)s;
    for (unsigned i=0;i<11;++i) fields[i]=hbl_mech_u32(p+12+4*i);
    if (!hbl_mech_fields_valid(s)) return 0;
    *epoch=hbl_mech_u32(p+8); *ns=hbl_mech_u32(p+56)|((uint64_t)hbl_mech_u32(p+60)<<32);
    return *ns!=0;
}
#endif
