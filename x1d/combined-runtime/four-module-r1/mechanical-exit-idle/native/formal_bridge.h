#ifndef HBL_FORMAL_BRIDGE_H
#define HBL_FORMAL_BRIDGE_H
#include <stdint.h>
#include <string.h>
#include "godox_formal_wave.h"

/* 本机同 uid 的 UI/worker 固定协议。时间为 CLOCK_MONOTONIC 毫秒。
 * 通信只请求无线业务；没有相机曝光、对焦或设置命令。 */
#define HBL_FORMAL_WORKER_SOCKET "/tmp/hbl-wireless-flash/formal-worker.sock"
#define HBL_FORMAL_UI_SOCKET "/tmp/hbl-wireless-flash/formal-ui.sock"
enum FormalKind {
    FORMAL_HELLO=1, FORMAL_HEARTBEAT=2, FORMAL_OPTIONS=3, FORMAL_GROUP=4,
    FORMAL_FLUSH=5, FORMAL_CANCEL=6, FORMAL_SHOT_END=7, FORMAL_BYE=8,FORMAL_TEST=9,
    FORMAL_WIRELESS=10, FORMAL_LAMP=11,
    FORMAL_STATUS=32, FORMAL_FLUSH_ACK=33
};
enum FormalValue {
    /* FV_EXPOSURE 是由原厂 TV 档位查表得到的名义曝光；不是实测曝光。
     * 电子同步只使用 observer 的 GFS3 本次实际参数。 */
    FV_MASTER=0,FV_POWER,FV_SYNC,FV_ELECTRONIC,FV_EXPOSURE_LO,FV_EXPOSURE_HI,
    FV_TOKEN,FV_GROUP,FV_ACTIVE,FV_TENTHS,
    FV_GROUP_A_ACTIVE,FV_GROUP_A_TENTHS,FV_GROUP_B_ACTIVE,FV_GROUP_B_TENTHS,
    FV_GROUP_C_ACTIVE,FV_GROUP_C_TENTHS,FV_GROUP_D_ACTIVE,FV_GROUP_D_TENTHS,
    FV_GROUP_E_ACTIVE,FV_GROUP_E_TENTHS,
    FV_GROUP_LAST_ACTIVE=40,FV_GROUP_LAST_TENTHS,
    FV_READY,FV_BUSY,FV_EVENT_ALIVE,FV_RESULT,FV_ACK_TOKEN,FV_ERROR,FV_PENDING,FV_SHOT_ACTIVE,
    FV_CHANNEL,FV_ID,FV_LAMPS,FV_RECONFIGURING,
    FV_COUNT=64
};
enum FormalResult { FORMAL_OK=0,FORMAL_REJECTED=1,FORMAL_TIMEOUT=2,
                    FORMAL_CANCELLED=3,FORMAL_RADIO_ERROR=4,FORMAL_UNAVAILABLE=5,FORMAL_GROUPS_UNSENT=6 };
enum { FORMAL_HEARTBEAT_MS=500,FORMAL_DISCONNECT_MS=2000,FORMAL_FLUSH_TIMEOUT_MS=6000,FORMAL_PACKET_BYTES=384 };
typedef struct {
    uint32_t magic,version,kind,session,sequence,time_lo,time_hi;
    uint32_t values[FV_COUNT];
    char text[100];
} FormalPacket;
static inline void formal_packet_init(FormalPacket *p,unsigned kind,uint32_t session,
                                      uint32_t sequence,uint64_t now) {
    memset(p,0,sizeof(*p)); p->magic=UINT32_C(0x31424648); p->version=2;
    if(kind==FORMAL_STATUS || kind==FORMAL_FLUSH_ACK) { p->values[FV_CHANNEL]=5; p->values[FV_ID]=5; }
    p->kind=kind;p->session=session;p->sequence=sequence;
    p->time_lo=(uint32_t)now;p->time_hi=(uint32_t)(now>>32);
}
static inline uint64_t formal_packet_time(const FormalPacket *p) {
    return (uint64_t)p->time_lo|((uint64_t)p->time_hi<<32);
}
static inline uint64_t formal_packet_exposure(const FormalPacket *p) {
    return (uint64_t)p->values[FV_EXPOSURE_LO]|((uint64_t)p->values[FV_EXPOSURE_HI]<<32);
}
static inline int formal_packet_valid(const FormalPacket *p,unsigned bytes) {
    if (!p || bytes!=FORMAL_PACKET_BYTES || sizeof(*p)!=FORMAL_PACKET_BYTES || p->magic!=UINT32_C(0x31424648) ||
        p->version!=2 || !p->session || !formal_packet_time(p)) return 0;
    if (p->kind==FORMAL_STATUS || p->kind==FORMAL_FLUSH_ACK) {
        if (p->values[FV_MASTER]>1 || p->values[FV_POWER]>1 || p->values[FV_SYNC]>1 ||
            p->values[FV_READY]>1 || p->values[FV_BUSY]>1 || p->values[FV_EVENT_ALIVE]>1 ||
            p->values[FV_SHOT_ACTIVE]>1 || p->values[FV_RESULT]>FORMAL_GROUPS_UNSENT || p->values[FV_ERROR]>FORMAL_GROUPS_UNSENT ||
            p->values[FV_PENDING]>HBL_FORMAL_GROUP_MASK || p->values[FV_LAMPS]>HBL_FORMAL_GROUP_MASK ||
            p->values[FV_RECONFIGURING]>1 || !hbl_formal_config_valid(p->values[FV_CHANNEL],p->values[FV_ID]) || !memchr(p->text,0,sizeof(p->text))) return 0;
        for (unsigned i=FV_ELECTRONIC;i<FV_GROUP_A_ACTIVE;++i) if (p->values[i]) return 0;
        for (unsigned i=FV_GROUP_A_ACTIVE;i<=FV_GROUP_LAST_ACTIVE;i+=2)
            if(p->values[i]>1 || p->values[i+1]>80) return 0;
        for (unsigned i=FV_RECONFIGURING+1;i<FV_COUNT;++i) if (p->values[i]) return 0;
        return p->kind==FORMAL_FLUSH_ACK ? p->values[FV_ACK_TOKEN]!=0 : (p->values[FV_ACK_TOKEN]==0 && p->values[FV_RESULT]==FORMAL_OK);
    }
    if (p->kind<FORMAL_HELLO || p->kind>FORMAL_LAMP ||
        (p->kind==FORMAL_HELLO ? p->sequence!=0 : p->sequence==0)) return 0;
    for (unsigned i=0;i<sizeof(p->text);++i) if (p->text[i]) return 0;
    uint64_t allowed=0;
    switch(p->kind) {
    case FORMAL_OPTIONS:
        allowed=7;
        if(p->values[FV_MASTER]>1 || p->values[FV_POWER]>1 || p->values[FV_SYNC]>1) return 0;
        break;
    case FORMAL_GROUP:
        allowed=(UINT64_C(1)<<FV_GROUP)|(UINT64_C(1)<<FV_ACTIVE)|(UINT64_C(1)<<FV_TENTHS);
        if(p->values[FV_GROUP]>=HBL_FORMAL_GROUPS || p->values[FV_ACTIVE]>1 || p->values[FV_TENTHS]>80) return 0;
        break;
    case FORMAL_FLUSH:
        allowed=(UINT64_C(1)<<FV_ELECTRONIC)|(UINT64_C(1)<<FV_EXPOSURE_LO)|(UINT64_C(1)<<FV_EXPOSURE_HI)|(UINT64_C(1)<<FV_TOKEN)|(UINT64_C(0xffffffff)<<FV_GROUP_A_ACTIVE);
        if(!p->values[FV_TOKEN] || p->values[FV_ELECTRONIC]>1 || !formal_packet_exposure(p) ||
            formal_packet_exposure(p)>UINT64_C(86400000000)) return 0;
        for(unsigned i=FV_GROUP_A_ACTIVE;i<=FV_GROUP_LAST_ACTIVE;i+=2)
            if(p->values[i]>1 || p->values[i+1]>80) return 0;
        break;
    case FORMAL_WIRELESS:
        allowed=(UINT64_C(1)<<FV_CHANNEL)|(UINT64_C(1)<<FV_ID);
        if(!hbl_formal_config_valid(p->values[FV_CHANNEL],p->values[FV_ID])) return 0;
        break;
    case FORMAL_LAMP:
        allowed=(UINT64_C(1)<<FV_GROUP)|(UINT64_C(1)<<FV_ACTIVE);
        if(p->values[FV_GROUP]>=HBL_FORMAL_GROUPS || p->values[FV_ACTIVE]>1) return 0;
        break;
    case FORMAL_CANCEL:case FORMAL_SHOT_END:
        allowed=UINT64_C(1)<<FV_TOKEN;if(!p->values[FV_TOKEN]) return 0;break;
    default:break;
    }
    for(unsigned i=0;i<FV_COUNT;++i) if(!(allowed&(UINT64_C(1)<<i)) && p->values[i]) return 0;
    return 1;
}
#endif
