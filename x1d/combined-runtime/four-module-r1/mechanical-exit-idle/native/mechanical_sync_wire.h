#ifndef HBL_MECHANICAL_SYNC_WIRE_H
#define HBL_MECHANICAL_SYNC_WIRE_H
#include <stddef.h>
#include <stdint.h>
#define HBL_MECH_MAGIC UINT32_C(0x31534d47) /* GMS1 */
#define HBL_MECH_IPC_MAGIC UINT32_C(0x314c4d47) /* GML1 */
#define HBL_MECH_SOCKET "/tmp/hbl-wireless-flash/mechanical-sync.sock"
#define HBL_MECH_A UINT32_C(0x800)
#define HBL_MECH_B UINT32_C(0x400)
#define HBL_MECH_CLOCK 4u
#define HBL_MECH_SOURCES 7u
#define HBL_MECH_EVENT_MASK 0x7fu
#define HBL_MECH_DONE 0x8000u
/* clear_flags 的 bit0/1 分别确认 A/B 旧保持位已经清零。 */
struct HblMechanicalSync {
    uint32_t magic, version, trial, clear_flags, cleared_status, sync_status;
    uint32_t timer_low, timer_high, timer_control, mode, source;
};
static inline uint32_t hbl_mech_u32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1]<<8 | (uint32_t)p[2]<<16 | (uint32_t)p[3]<<24;
}
static inline void hbl_mech_put32(uint8_t *p,uint32_t v) {
    for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(v>>(i*8));
}
static inline int hbl_mech_fields_valid(const struct HblMechanicalSync *s) {
    if (!s || s->magic!=HBL_MECH_MAGIC || s->version!=1 || !s->trial ||
        s->mode>1 || s->source!=3 || (s->clear_flags&~0xff07u)) return 0;
    if ((s->clear_flags&1) && (s->cleared_status&HBL_MECH_A)) return 0;
    if ((s->clear_flags&2) && (s->cleared_status&HBL_MECH_B)) return 0;
    if ((s->clear_flags&HBL_MECH_CLOCK) && !(s->timer_control&1)) return 0;
    const unsigned events=(s->clear_flags>>8)&HBL_MECH_EVENT_MASK;
    if ((events&1) && (!(s->clear_flags&1) || !(s->sync_status&HBL_MECH_A))) return 0;
    if ((events&2) && (!(s->clear_flags&2) || !(s->sync_status&HBL_MECH_B))) return 0;
    if ((events&4) && !(s->sync_status&4)) return 0;
    if ((events&8) && (s->sync_status&1)) return 0;
    if ((events&16) && !(s->sync_status&2)) return 0;
    if ((events&32) && !(s->sync_status&8)) return 0;
    if ((events&64) && !(s->sync_status&1)) return 0;
    return 1;
}
/* 0=A，1=B，2=启动保持置位，3=退出空闲，4=状态1置位，5=状态3置位，6=返回空闲。
 * 后四项命名均为软件状态；不将其解释成物理曝光边界。 */
static inline int hbl_mech_confirmed(const struct HblMechanicalSync *s,unsigned source) {
    if (!hbl_mech_fields_valid(s) || source>=HBL_MECH_SOURCES || !(s->clear_flags&HBL_MECH_CLOCK) ||
        !(s->clear_flags&(1u<<(source+8)))) return 0;
    if (source<2) return (s->clear_flags&(1u<<source)) && (s->sync_status&(source ? HBL_MECH_B : HBL_MECH_A));
    const uint32_t masks[5]={4,1,2,8,1};
    return source==3 ? !(s->sync_status&1) : !!(s->sync_status&masks[source-2]);
}
static inline int hbl_parse_mech_message(const uint8_t *p,size_t n,struct HblMechanicalSync *s) {
    if (!p || !s || n!=260 || hbl_mech_u32(p)!=UINT32_C(0x05010009)) return 0;
    uint32_t *fields=(uint32_t *)s;
    for (unsigned i=0;i<11;++i) fields[i]=hbl_mech_u32(p+4+4*i);
    if (!hbl_mech_fields_valid(s)) return 0;
    for (size_t i=48;i<n;++i) if (p[i]) return 0;
    return 1;
}
static inline void hbl_pack_mech_ipc(uint8_t p[64],uint32_t epoch,
                                    const struct HblMechanicalSync *s,uint64_t ns) {
    hbl_mech_put32(p,HBL_MECH_IPC_MAGIC); hbl_mech_put32(p+4,1); hbl_mech_put32(p+8,epoch);
    const uint32_t *fields=(const uint32_t *)s;
    for (unsigned i=0;i<11;++i) hbl_mech_put32(p+12+4*i,fields[i]);
    hbl_mech_put32(p+56,(uint32_t)ns); hbl_mech_put32(p+60,(uint32_t)(ns>>32));
}
static inline int hbl_parse_mech_ipc(const uint8_t *p,size_t n,uint32_t *epoch,
                                    struct HblMechanicalSync *s,uint64_t *ns) {
    if (!p || !epoch || !s || !ns || n!=64 || hbl_mech_u32(p)!=HBL_MECH_IPC_MAGIC ||
        hbl_mech_u32(p+4)!=1 || !hbl_mech_u32(p+8)) return 0;
    uint32_t *fields=(uint32_t *)s;
    for (unsigned i=0;i<11;++i) fields[i]=hbl_mech_u32(p+12+4*i);
    if (!hbl_mech_fields_valid(s)) return 0;
    *epoch=hbl_mech_u32(p+8); *ns=hbl_mech_u32(p+56)|((uint64_t)hbl_mech_u32(p+60)<<32);
    return *ns!=0;
}
#endif
