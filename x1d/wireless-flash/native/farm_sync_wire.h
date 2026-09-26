#ifndef HBL_FARM_SYNC_WIRE_H
#define HBL_FARM_SYNC_WIRE_H
#include <stddef.h>
#include <stdint.h>

#define HBL_SYNC_MAGIC UINT32_C(0x33534647) /* GFS3 */
#define HBL_SYNC_IPC_MAGIC UINT32_C(0x334c5347) /* GSL3 */
#define HBL_SYNC_CLEAR 1u
#define HBL_SYNC_SEEN 2u
#define HBL_SYNC_CLOCK 4u
#define HBL_SYNC_STATUS_BIT UINT32_C(0x400)
#define HBL_SYNC_SOURCES 3u
/* flags 高字节：0=B 保持位，1=B 后首次进度读数，2=正常请求停止前。
 * source 1/2 的 cleared_status 保存原厂进度返回值，不解释为行数。
 */
static inline unsigned hbl_sync_source(uint32_t flags) { return flags>>8; }
#define HBL_SYNC_SOCKET "/tmp/hbl-wireless-flash/fpga-sync.sock"

/* 仅含同步观察结果，附带本次曝光微秒参数，不包含照片数据。 */
struct HblFarmSync {
    uint32_t magic, version, shot, flags, cleared_status, sync_status;
    uint32_t timer_low, timer_high, timer_control;
    uint32_t exposure_low, exposure_high;
};

static inline uint32_t hbl_sync_u32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static inline void hbl_sync_put32(uint8_t *p, uint32_t v) {
    for (unsigned i=0;i<4;++i) p[i]=(uint8_t)(v >> (8*i));
}
static inline int hbl_sync_fields_valid(const struct HblFarmSync *p) {
    if (!p || p->magic!=HBL_SYNC_MAGIC || p->version!=3 || !p->shot ||
        hbl_sync_source(p->flags)>=HBL_SYNC_SOURCES || (p->flags&0xf8)) return 0;
    const unsigned source=hbl_sync_source(p->flags);
    if (source==0 && (p->flags&HBL_SYNC_CLEAR) && (p->cleared_status&HBL_SYNC_STATUS_BIT)) return 0;
    if ((p->flags&HBL_SYNC_SEEN) && !(p->flags&HBL_SYNC_CLEAR)) return 0;
    if (source==0 && (p->flags&HBL_SYNC_SEEN) && !(p->sync_status&HBL_SYNC_STATUS_BIT)) return 0;
    if ((p->flags&HBL_SYNC_CLOCK) && !(p->timer_control&1)) return 0;
    return 1;
}

/* 固定原厂 testd_tx_event 容器：4 字节头和 256 字节 payload。
 * 只有本候选的完整标识及零尾部才属于自有消息，其余原厂消息全部透传。
 */
static inline int hbl_parse_sync_message(const uint8_t *p, size_t n, struct HblFarmSync *out) {
    if (!p || !out || n!=260 || p[0]!=9 || p[1] || p[2]!=1 || p[3]!=5) return 0;
    uint32_t *fields=(uint32_t *)out;
    for (unsigned i=0;i<11;++i) fields[i]=hbl_sync_u32(p+4+4*i);
    if (!hbl_sync_fields_valid(out)) return 0;
    for (size_t i=48;i<n;++i) if (p[i]) return 0;
    return 1;
}

/* Linux 接收时间只表示消息到达；不把 FARM 计数器与 Linux 时钟混算。 */
static inline void hbl_pack_sync_ipc(uint8_t out[64], uint32_t epoch,
                                    const struct HblFarmSync *sample, uint64_t arrival_ns) {
    hbl_sync_put32(out,HBL_SYNC_IPC_MAGIC);
    hbl_sync_put32(out+4,3);
    hbl_sync_put32(out+8,epoch);
    const uint32_t *fields=(const uint32_t *)sample;
    for (unsigned i=0;i<11;++i) hbl_sync_put32(out+12+4*i,fields[i]);
    hbl_sync_put32(out+56,(uint32_t)arrival_ns);
    hbl_sync_put32(out+60,(uint32_t)(arrival_ns>>32));
}
static inline int hbl_parse_sync_ipc(const uint8_t *p, size_t n, uint32_t *epoch,
                                     struct HblFarmSync *sample, uint64_t *arrival_ns) {
    if (!p || !epoch || !sample || !arrival_ns || n!=64 ||
        hbl_sync_u32(p)!=HBL_SYNC_IPC_MAGIC || hbl_sync_u32(p+4)!=3 || !hbl_sync_u32(p+8)) return 0;
    uint32_t *fields=(uint32_t *)sample;
    for (unsigned i=0;i<11;++i) fields[i]=hbl_sync_u32(p+12+4*i);
    if (!hbl_sync_fields_valid(sample)) return 0;
    *epoch=hbl_sync_u32(p+8);
    *arrival_ns=hbl_sync_u32(p+56) | ((uint64_t)hbl_sync_u32(p+60)<<32);
    return *arrival_ns!=0;
}
#endif
