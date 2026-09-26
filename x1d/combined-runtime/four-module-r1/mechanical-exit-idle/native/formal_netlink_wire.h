#ifndef HBL_FORMAL_NETLINK_WIRE_H
#define HBL_FORMAL_NETLINK_WIRE_H
#include "rf_netlink_wire.h"
#include "godox_formal_wave.h"

/* 只开放 formal_flash.c 的正常驱动 selector；不开放任意 PHY 寄存器。 */
static inline int formal_selector_allowed(uint32_t selector) {
    switch (selector) {
    case 0: case 14: case 15: case 16: case 17: case 18: case 19: case 20:
    case 26: case 27: case 40: case 48: return 1;
    default: return (selector>=512 && selector<512+HBL_FORMAL_CONTROL_WAVES) ||
        (selector>=HBL_FORMAL_CONFIG_BASE && selector<HBL_FORMAL_CONFIG_BASE+HBL_FORMAL_CONFIG_COUNT);
    }
}
static inline size_t formal_nl_register_request(uint8_t *out,size_t cap,uint16_t family,
                                               uint32_t seq,uint32_t port,uint32_t ifindex,
                                               uint32_t selector) {
    uint8_t value[4],dcmd[28]; size_t used;
    if (!out || family<17 || !ifindex || !formal_selector_allowed(selector)) return 0;
    used=rf_nl_begin(out,cap,family,seq,port,103);
    if (!used) return 0;
    rf_put32(value,ifindex); if (!rf_nl_add(out,cap,&used,3,value,4)) return 0;
    rf_put32(value,0x1018); if (!rf_nl_add(out,cap,&used,195,value,4)) return 0;
    rf_put32(value,1); if (!rf_nl_add(out,cap,&used,196,value,4)) return 0;
    memset(dcmd,0,sizeof(dcmd));
    rf_put32(dcmd,94); rf_put32(dcmd+4,8); rf_put32(dcmd+8,20);
    rf_put32(dcmd+20,selector); rf_put32(dcmd+24,2);
    if (!rf_nl_add(out,cap,&used,197,dcmd,sizeof(dcmd))) return 0;
    return used;
}
#endif
