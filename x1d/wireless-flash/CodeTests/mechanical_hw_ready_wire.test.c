#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include "../build/mechanical-hw-ready-candidate/hardware_ready_netlink_wire.h"
#include "../native/mechanical_prepared_request.h"

int main(void) {
    unsigned accepted=0;
    uint8_t out[128];
    for (unsigned selector=0;selector<65536;++selector) {
        size_t n=rf_nl_register_request(out,sizeof(out),30,7,42,2,selector);
        assert(!!n==(selector==0 || selector==40 || selector==41));
        if (n) {
            const uint8_t *attribute; size_t length;
            assert(rf_nl_attribute(out+20,n-20,197,&attribute,&length)==1);
            assert(length==28 && rf_le32(attribute)==94 && rf_le32(attribute+20)==selector);
            ++accepted;
        }
    }
    MechanicalPreparedRequest prepared={0};
    assert(mechanical_prepare_request(&prepared,30,7,42,2));
    const uint8_t *attribute; size_t length;
    assert(rf_nl_attribute(prepared.bytes+20,prepared.size-20,197,&attribute,&length)==1);
    assert(rf_le32(attribute+20)==40);
    assert(mechanical_consume_request(&prepared,7));
    assert(!mechanical_consume_request(&prepared,7));
    printf("{\"passed\":true,\"selectorsChecked\":65536,\"allowedSelectors\":%u,\"fireRemainsPreencoded\":true,\"hardwareRequests\":0}\n",accepted);
    return 0;
}
