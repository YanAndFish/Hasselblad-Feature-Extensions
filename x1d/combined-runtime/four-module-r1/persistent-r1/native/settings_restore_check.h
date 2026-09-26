#ifndef HBL_SETTINGS_RESTORE_CHECK_H
#define HBL_SETTINGS_RESTORE_CHECK_H
#include "formal_bridge.h"
// 关闭时不要求 radio held/ready；连接初始化遗留的 unavailable/cancelled 不是设置拒绝。
static inline bool hblRestoreIdleStatus(const FormalPacket &p) {
    return !p.values[FV_BUSY] && !p.values[FV_RECONFIGURING] && !p.values[FV_SHOT_ACTIVE];
}
static inline bool hblRestoreInactiveError(unsigned error) {
    return error==FORMAL_OK || error==FORMAL_UNAVAILABLE || error==FORMAL_CANCELLED;
}
static inline bool hblRestoreWirelessAck(const FormalPacket &p,unsigned channel,unsigned id) {
    return hblRestoreIdleStatus(p) && !p.values[FV_MASTER] &&
        hblRestoreInactiveError(p.values[FV_ERROR]) && p.values[FV_CHANNEL]==channel && p.values[FV_ID]==id;
}
static inline bool hblRestoreOptionsAck(const FormalPacket &p,bool master,bool power,bool sync) {
    if(!hblRestoreIdleStatus(p) || p.values[FV_MASTER]!=unsigned(master) ||
        p.values[FV_POWER]!=unsigned(power) || p.values[FV_SYNC]!=unsigned(sync))return false;
    if(!master)return hblRestoreInactiveError(p.values[FV_ERROR]);
    return p.values[FV_ERROR]==FORMAL_OK && (p.values[FV_READY] || (!power && !sync));
}
#endif
