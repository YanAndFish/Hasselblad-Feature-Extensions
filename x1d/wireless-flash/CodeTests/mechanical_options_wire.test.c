#include "../build/mechanical-options-candidate/options_netlink_wire.h"
#include "../build/mechanical-options-candidate/options_prepared_request.h"
#include "../build/mechanical-options-candidate/options_rf_bridge.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
int main(void) {
    unsigned n;
    for (n=0;n<65536;++n) {
        unsigned char bytes[128];
        const size_t result=rf_nl_register_request(bytes,sizeof(bytes),0x20,1,123,2,n);
        assert(!!result==(n==0 || n==40 || n==41 || n==42 || n==43));
    }
    for (n=0;n<2;++n) {
        MechanicalPreparedRequest request={0}; unsigned char expected[128];
        assert(mechanical_prepare_request(&request,0x20,8,123,2,n));
        size_t size=rf_nl_register_request(expected,sizeof(expected),0x20,9,123,2,n ? 43 : 40);
        assert(request.size==size && !memcmp(expected,request.bytes,size));
        assert(mechanical_consume_request(&request,8));
        assert(!mechanical_consume_request(&request,8));
    }
    MechanicalPreparedRequest invalid={0};
    assert(!mechanical_prepare_request(&invalid,0x20,8,123,2,2));
    RfBridgePacket packet;
    rf_bridge_init(&packet,RF_UI_CONFIG,1,1,1);
    packet.values[RV_POWER]=10;
    assert(sizeof(packet)==256 && rf_bridge_valid(&packet,sizeof(packet)));
    for (n=0;n<4;++n) {
        packet.values[RV_PER_SHOT]=n&1; packet.values[RV_SAME_PROCESS]=n>>1;
        assert(rf_bridge_settings_valid(&packet));
    }
    packet.values[RV_PER_SHOT]=2; assert(!rf_bridge_settings_valid(&packet));
    packet.values[RV_PER_SHOT]=0; packet.values[RV_SAME_PROCESS]=2; assert(!rf_bridge_settings_valid(&packet));
    packet.version=2; assert(!rf_bridge_valid(&packet,sizeof(packet)));
    puts("two-mode wire checks passed; selectors=65536; hardware=0");
    return 0;
}
