#include "../native/formal_policy.h"
#include "../native/settings_restore_check.h"
#include <cassert>
#include <cstdio>
#include <initializer_list>
int main() {
    FormalPolicy policy;policy.newSession(1000000);policy.setEventAlive(true,1000001);
    assert(policy.setOptions(0,1,1,1000002));assert(policy.setWireless(5,5,1000003));
    assert(policy.next(1000004).action==FormalPolicy::None);
    FormalPacket p={};p.values[FV_CHANNEL]=policy.channel;p.values[FV_ID]=policy.wirelessId;
    p.values[FV_ERROR]=policy.lastError;p.values[FV_MASTER]=policy.master;
    p.values[FV_READY]=policy.restored();p.values[FV_BUSY]=policy.busy();
    p.values[FV_POWER]=policy.powerUpdates;p.values[FV_SYNC]=policy.flashSync;
    assert(!p.values[FV_READY] && p.values[FV_ERROR]==FORMAL_UNAVAILABLE);
    assert(hblRestoreWirelessAck(p,5,5));assert(hblRestoreOptionsAck(p,false,true,true));
    assert(!hblRestoreWirelessAck(p,6,5));assert(!hblRestoreWirelessAck(p,5,6));
    for(unsigned error=0;error<=FORMAL_GROUPS_UNSENT;++error) {
        p.values[FV_ERROR]=error;
        assert(hblRestoreOptionsAck(p,false,true,true)==hblRestoreInactiveError(error));
    }
    p.values[FV_ERROR]=FORMAL_OK;
    for(unsigned f:{FV_BUSY,FV_RECONFIGURING,FV_SHOT_ACTIVE}) {
        p.values[f]=1;assert(!hblRestoreWirelessAck(p,5,5));assert(!hblRestoreOptionsAck(p,false,true,true));p.values[f]=0;
    }
    p.values[FV_MASTER]=1;assert(!hblRestoreWirelessAck(p,5,5));assert(!hblRestoreOptionsAck(p,true,true,true));
    p.values[FV_READY]=1;assert(hblRestoreOptionsAck(p,true,true,true));
    assert(!hblRestoreOptionsAck(p,false,true,true));assert(!hblRestoreOptionsAck(p,true,false,true));
    p.values[FV_ERROR]=FORMAL_RADIO_ERROR;assert(!hblRestoreOptionsAck(p,true,true,true));
    std::puts("settings-restore: default-off completes without radio open; invalid status rejected; hardware=0");
}
