#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../native/farm_sync_wire.h"

int main(void) {
    unsigned checks=0;
    uint8_t raw[261]={9,0,1,5},wire[65]={0};
    struct HblFarmSync sample={HBL_SYNC_MAGIC,3,8,7,0x3334,0x3734,100,7,1,250000,0},parsed;
    const uint32_t *fields=(const uint32_t *)&sample;
    for (unsigned i=0;i<11;++i) hbl_sync_put32(raw+4+4*i,fields[i]);
    for (unsigned length=0;length<=261;++length) {
        assert(hbl_parse_sync_message(raw,length,&parsed)==(length==260)); ++checks;
    }
    assert(memcmp(&sample,&parsed,sizeof(sample))==0); ++checks;
    const unsigned guarded[]={0,1,2,3,4,5,6,7,8,48,259};
    for (unsigned i=0;i<sizeof(guarded)/sizeof(*guarded);++i) {
        raw[guarded[i]]^=1;
        assert(!hbl_parse_sync_message(raw,260,&parsed)); ++checks;
        raw[guarded[i]]^=1;
    }
    assert(!hbl_parse_sync_message(NULL,260,&parsed)); ++checks;
    assert(!hbl_parse_sync_message(raw,260,NULL)); ++checks;
    sample.flags=3; sample.cleared_status|=HBL_SYNC_STATUS_BIT;
    assert(!hbl_sync_fields_valid(&sample)); ++checks;
    sample.cleared_status=0; sample.sync_status=0;
    assert(!hbl_sync_fields_valid(&sample)); ++checks;
    sample.flags=4; sample.timer_control=0;
    assert(!hbl_sync_fields_valid(&sample)); ++checks;
    sample.flags=7; sample.sync_status=HBL_SYNC_STATUS_BIT; sample.timer_control=1;
    uint32_t epoch=0; uint64_t at=0;
    hbl_pack_sync_ipc(wire,123,&sample,UINT64_C(9876543210));
    for (unsigned length=0;length<=65;++length) {
        assert(hbl_parse_sync_ipc(wire,length,&epoch,&parsed,&at)==(length==64)); ++checks;
    }
    assert(epoch==123 && at==UINT64_C(9876543210) && !memcmp(&sample,&parsed,sizeof(sample))); ++checks;
    hbl_sync_put32(wire+8,0); assert(!hbl_parse_sync_ipc(wire,64,&epoch,&parsed,&at)); ++checks;
    hbl_sync_put32(wire+8,123); hbl_sync_put32(wire+56,0); hbl_sync_put32(wire+60,0);
    assert(!hbl_parse_sync_ipc(wire,64,&epoch,&parsed,&at)); ++checks;
    printf("{\"passed\":true,\"checks\":%u,\"hardwareRequests\":0}\n",checks);
    return 0;
}
