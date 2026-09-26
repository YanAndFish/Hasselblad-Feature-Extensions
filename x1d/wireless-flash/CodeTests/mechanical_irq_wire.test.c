#include "../build/mechanical-irq-candidate/irq_rf_core.h"
#include "../build/mechanical-irq-candidate/options_rf_bridge.h"
#include "../build/mechanical-irq-candidate/options_prepared_request.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>

static void check_source(const char *path,unsigned source) {
    uint8_t packet[260],ipc[64];
    FILE *f=fopen(path,"rb"); assert(f);
    assert(fread(packet,1,sizeof(packet),f)==sizeof(packet));
    assert(fgetc(f)==EOF); fclose(f);
    struct HblMechanicalSync s,decoded;
    assert(hbl_parse_mech_message(packet,sizeof(packet),&s));
    assert(hbl_mech_confirmed(&s,source));
    for (unsigned i=0;i<7;++i) assert(hbl_mech_confirmed(&s,i)==(i==source));
    s.sync_status=source==2 ? 1 : 5;
    assert(hbl_mech_confirmed(&s,source)); /* 到达后的状态极性不取代中断编号。 */
    uint32_t epoch; uint64_t at;
    hbl_pack_mech_ipc(ipc,7,&s,UINT64_C(1000000000));
    assert(hbl_parse_mech_ipc(ipc,64,&epoch,&decoded,&at));
    assert(epoch==7 && at==1000000000 && !memcmp(&s,&decoded,sizeof(s)));
    ipc[4]=1; assert(!hbl_parse_mech_ipc(ipc,64,&epoch,&decoded,&at));
    packet[8]=1; assert(!hbl_parse_mech_message(packet,260,&decoded)); packet[8]=2;
    packet[259]=1; assert(!hbl_parse_mech_message(packet,260,&decoded)); packet[259]=0;
    assert(!hbl_parse_mech_message(packet,259,&decoded));
    for (unsigned delay=0;delay<=5000000;delay+=10) {
        RfCore c; rf_init(&c,0); assert(rf_configure(&c,1,source,delay));
        assert(mechanical_rf_accept(&c,&s,1000000,1000000,999999));
        assert(c.deadline_us==1000000+delay);
        assert(!mechanical_rf_accept(&c,&s,1000000,1000000,999999));
        if (delay) assert(!rf_due(&c,1000000+delay-1));
        assert(rf_due(&c,1000000+delay)); assert(!rf_due(&c,1000000+delay));
    }
    RfCore c; rf_init(&c,0); assert(rf_configure(&c,1,source,1000));
    assert(mechanical_rf_accept(&c,&s,1000000,1000000,999999));
    assert(rf_configure(&c,1,source==2?3:2,1000)); assert(!rf_due(&c,1001000));
    assert(rf_configure(&c,1,source,1000)); s.trial++;
    assert(mechanical_rf_accept(&c,&s,2000000,2000000,999999));
    rf_cancel(&c); assert(!rf_due(&c,2001000));
    s.trial++; assert(!mechanical_rf_accept(&c,&s,3000000,3250001,999999));
    s.version=1; assert(!hbl_mech_fields_valid(&s)); s.version=2;
    s.clear_flags|=HBL_MECH_DONE; assert(!hbl_mech_fields_valid(&s));
    s.clear_flags=HBL_MECH_DONE|HBL_MECH_CLOCK;
    assert(hbl_mech_fields_valid(&s) && !hbl_mech_confirmed(&s,source));
    s.timer_control=0; assert(!hbl_mech_fields_valid(&s));
}

int main(int argc,char **argv) {
    assert(argc==3); check_source(argv[1],2); check_source(argv[2],3);
    RfBridgePacket p; rf_bridge_init(&p,RF_UI_CONFIG,1,1,1);
    p.values[RV_POWER]=10; assert(rf_bridge_valid(&p,256));
    for (unsigned i=0;i<7;++i) {
        p.values[RV_SOURCE]=i;
        assert(rf_bridge_settings_valid(&p)==(i==2 || i==3));
    }
    p.values[RV_SOURCE]=2; p.values[RV_SAME_PROCESS]=1;
    assert(!rf_bridge_settings_valid(&p)); p.values[RV_SAME_PROCESS]=0;
    p.version=3; assert(!rf_bridge_valid(&p,256));
    for (unsigned i=0;i<2;++i) {
        MechanicalPreparedRequest r={0}; uint8_t expected[128];
        assert(mechanical_prepare_request(&r,0x20,8,123,2,i));
        size_t n=rf_nl_register_request(expected,128,0x20,9,123,2,i?43:40);
        assert(n==r.size && !memcmp(expected,r.bytes,n));
        assert(mechanical_consume_request(&r,8)); assert(!mechanical_consume_request(&r,8));
    }
    puts("IRQ protocol and deadline cases passed; delay cases=1000002; hardware=0");
    return 0;
}
