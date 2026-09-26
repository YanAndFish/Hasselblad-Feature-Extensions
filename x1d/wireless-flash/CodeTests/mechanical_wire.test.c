#include "../native/mechanical_rf_core.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "../native/mechanical_rf_bridge.h"
#include "../native/mechanical_prepared_request.h"
int main(void) {
    struct HblMechanicalSync s={HBL_MECH_MAGIC,1,1,0x7707,0x3001,0x3c0f,3,7,1,0,3},parsed;
    uint8_t ipc[64],message[260]={9,0,1,5};
    uint32_t epoch; uint64_t arrival;
    hbl_pack_mech_ipc(ipc,42,&s,1000000000);
    assert(hbl_parse_mech_ipc(ipc,sizeof(ipc),&epoch,&parsed,&arrival));
    assert(epoch==42 && arrival==1000000000 && !memcmp(&s,&parsed,sizeof(s)));
    for(unsigned i=0;i<11;++i) hbl_mech_put32(message+4+4*i,((uint32_t *)&s)[i]);
    assert(hbl_parse_mech_message(message,sizeof(message),&parsed));
    message[259]=1; assert(!hbl_parse_mech_message(message,sizeof(message),&parsed)); message[259]=0;
    message[4]^=1; assert(!hbl_parse_mech_message(message,sizeof(message),&parsed)); message[4]^=1;
    for(unsigned source=0;source<7;++source) {
        RfCore c; rf_init(&c,1);
        s.sync_status=source==3 ? 0x3c0e : 0x3c0f;
        s.clear_flags=7|(1u<<(source+8));
        assert(rf_configure(&c,1,source,10000));
        assert(mechanical_rf_accept(&c,&s,1000000,1001000,999000));
        assert(!mechanical_rf_accept(&c,&s,1000000,1001000,999000));
        assert(!rf_due(&c,1009000)); assert(rf_due(&c,1010000)); assert(!rf_due(&c,1011000));
        assert(c.enabled);
        assert(!mechanical_rf_accept(&c,&s,1012000,1012000,999000));
        ++s.trial;
        assert(mechanical_rf_accept(&c,&s,1020000,1020000,999000));
        assert(rf_due(&c,1030000)); assert(c.enabled);
    }
    s.clear_flags=0x207;
    RfCore c; rf_init(&c,1); assert(rf_configure(&c,1,1,0));
    assert(!mechanical_rf_accept(&c,&s,1000000,1251000,999000));
    assert(!mechanical_rf_accept(&c,&s,1000000,1000000,1001000));
    s.clear_flags=0x203; assert(!mechanical_rf_accept(&c,&s,1000000,1000000,999000));
    s.clear_flags=0x207; s.cleared_status|=HBL_MECH_B;
    assert(!hbl_mech_fields_valid(&s)); s.cleared_status&=~HBL_MECH_B;
    assert(!rf_configure(&c,1,7,0)); assert(!rf_configure(&c,1,0,5001000));
    assert(rf_configure(&c,0,1,0)); assert(rf_configure(&c,1,1,0));
    ++s.trial;
    assert(mechanical_rf_accept(&c,&s,1000000,1000000,999000));
    assert(!rf_due(&c,1251000)); assert(c.enabled && !c.pending);
    // 更改信号、延迟、关闭重开均不能重用同一个请求。
    assert(rf_configure(&c,1,0,20000)); assert(c.enabled);
    s.clear_flags=0x107;
    assert(!mechanical_rf_accept(&c,&s,1300000,1300000,999000));
    assert(rf_configure(&c,0,0,20000)); assert(rf_configure(&c,1,0,20000));
    assert(!mechanical_rf_accept(&c,&s,1301000,1301000,999000));
    ++s.trial; assert(mechanical_rf_accept(&c,&s,1400000,1400000,999000));
    assert(rf_configure(&c,1,0,30000)); assert(!c.pending && c.enabled);
    assert(!rf_due(&c,1420000));
    assert(!mechanical_rf_accept(&c,&s,1421000,1421000,999000));
    ++s.trial; assert(mechanical_rf_accept(&c,&s,1500000,1500000,999000));
    rf_cancel(&c); assert(!rf_due(&c,1530000) && c.enabled);
    assert(!mechanical_rf_accept(&c,&s,1531000,1531000,999000));
    ++s.trial; assert(mechanical_rf_accept(&c,&s,1600000,1600000,999000));
    ++s.trial; mechanical_rf_begin(&c,s.trial);
    assert(!c.pending && c.enabled);
    assert(!rf_due(&c,1630000));
    assert(mechanical_rf_accept(&c,&s,1700000,1700000,999000));
    assert(rf_due(&c,1730000)); assert(!rf_due(&c,1731000));
    --s.trial; assert(!mechanical_rf_accept(&c,&s,1800000,1800000,999000));
    ++s.trial; ++s.trial;
    assert(rf_configure(&c,0,0,30000));
    assert(!mechanical_rf_accept(&c,&s,1800000,1800000,999000));
    assert(!rf_due(&c,1830000));
    assert(rf_configure(&c,1,0,30000)); ++s.trial;
    assert(mechanical_rf_accept(&c,&s,1900000,1900000,999000));
    assert(!rf_due(&c,1800000) && !c.enabled && !c.pending);
    // 设置前已到达但尚未处理的开始报文，不能让后续包沿用新设置发射。
    assert(rf_configure(&c,1,1,0)); ++s.trial; s.clear_flags=0x207;
    assert(!mechanical_rf_accept(&c,&s,2000000,2002000,2001000));
    assert(!mechanical_rf_accept(&c,&s,2003000,2003000,2001000));
    ++s.trial; assert(mechanical_rf_accept(&c,&s,2100000,2100000,2001000));
    assert(rf_due(&c,2100000) && c.enabled);
    // 亚毫秒边界：10 us 不得被截断为0或向下折算成整毫秒。
    rf_init(&c,1); s.trial=1; s.clear_flags=0x207;
    assert(rf_configure(&c,1,1,10));
    assert(mechanical_rf_accept(&c,&s,1000999,1001000,1000000));
    assert(c.deadline_us==1001009);
    assert(!rf_due(&c,1001008)); assert(rf_due(&c,1001009));
    assert(!rf_due(&c,1001010) && c.enabled);
    assert(!rf_configure(&c,1,1,11));
    assert(rf_configure(&c,1,1,7010)); ++s.trial;
    assert(mechanical_rf_accept(&c,&s,2000001,2000001,1000000));
    assert(c.deadline_us==2007011);
    assert(!rf_due(&c,2007010)); assert(rf_due(&c,2007011));
    RfBridgePacket bridge;
    rf_bridge_init(&bridge,RF_UI_CONFIG,1,1,1000);
    bridge.values[RV_POWER]=10; bridge.values[RV_DELAY]=7010;
    assert(rf_bridge_valid(&bridge,sizeof(bridge)) && rf_bridge_settings_valid(&bridge));
    bridge.values[RV_DELAY]=7011; assert(!rf_bridge_settings_valid(&bridge));
    bridge.values[RV_DELAY]=5000010; assert(!rf_bridge_settings_valid(&bridge));
    bridge.magic=0x31424d48; bridge.version=1;
    assert(!rf_bridge_valid(&bridge,sizeof(bridge))); // 旧毫秒机械包必须拒收
    // 预编码字节与既有白名单构造器逐字节一致；每次资格只可消费一次。
    MechanicalPreparedRequest prepared={0}; uint8_t expected[128];
    for (uint32_t seq=0;seq<1000;++seq) {
        assert(mechanical_prepare_request(&prepared,33,seq,77,5));
        size_t n=rf_nl_register_request(expected,sizeof(expected),33,seq+1,77,5,40);
        assert(n==prepared.size && !memcmp(expected,prepared.bytes,n));
        assert(!mechanical_consume_request(&prepared,seq+1));
        assert(mechanical_consume_request(&prepared,seq));
        assert(!mechanical_consume_request(&prepared,seq));
    }
    assert(!mechanical_prepare_request(&prepared,16,0,77,5));
    assert(!mechanical_prepare_request(&prepared,33,0,77,0));
    assert(!mechanical_prepare_request(&prepared,33,UINT32_MAX,77,5));
    assert(mechanical_prepare_request(&prepared,33,UINT32_MAX-1,77,5));
    assert(mechanical_consume_request(&prepared,UINT32_MAX-1));
    assert(!mechanical_prepare_request(&prepared,33,UINT32_MAX,77,5));
    // 临界点附近只推迟界面发布，不消费触发资格；长延迟继续正常心跳。
    c.pending=1; c.enabled=1; c.deadline_us=5000000; c.consumed=1;
    RfCore before_defer=c;
    assert(!mechanical_defer_status(&c,1000000));
    assert(!mechanical_defer_status(&c,4997999));
    assert(mechanical_defer_status(&c,4998000));
    assert(mechanical_defer_status(&c,5000000));
    assert(mechanical_defer_status(&c,5000001));
    assert(!memcmp(&c,&before_defer,sizeof(c)));
    c.deadline_us=UINT64_MAX; assert(mechanical_defer_status(&c,UINT64_MAX-1));
    c.pending=0; assert(!mechanical_defer_status(&c,UINT64_MAX));
    puts("{\"passed\":true,\"sources\":7,\"continuous_trials\":true,\"microsecond_deadlines\":true,\"prepared_requests\":1000,\"deadline_status_guard\":true,\"hardware_requests\":0}");
    return 0;
}
