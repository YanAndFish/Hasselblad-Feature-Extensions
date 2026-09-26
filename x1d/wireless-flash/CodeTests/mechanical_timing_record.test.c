#include "../native/mechanical_timing_record.h"
#include "../native/mechanical_rf_core.h"
#include <stdio.h>
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
_Static_assert(sizeof(HblTimingEvent)==72,"fixed record ABI");
int main(void)
{
    HblTimingRing ring={0}; HblTimingEvent event={0};
    RfCore before, after;
    CHECK(!hbl_timing_can_flush(&ring,0,0,0));
    for (unsigned i=0;i<HBL_TIMING_CAPACITY+17;++i) {
        event.mono_us=i; event.hardware_ticks=UINT64_C(0x100000000)+i;
        event.kind=HBL_TIMING_SAMPLE; event.trial=i+1;
        hbl_timing_push(&ring,&event);
    }
    CHECK(ring.count==HBL_TIMING_CAPACITY && ring.overwritten==17);
    CHECK(ring.total==HBL_TIMING_CAPACITY+17 && hbl_timing_first(&ring)==17);
    for (unsigned i=0;i<ring.count;++i) {
        const HblTimingEvent *p=&ring.events[(hbl_timing_first(&ring)+i)%HBL_TIMING_CAPACITY];
        CHECK(p->mono_us==i+17 && p->hardware_ticks==UINT64_C(0x100000000)+i+17);
    }
    for (unsigned mask=0;mask<8;++mask)
        CHECK(hbl_timing_can_flush(&ring,mask&1,mask&2,mask&4)==(mask==0));
    /* 同样的迟到消息：记录之后仍沿用原 deadline，不偷偷扣减或延长。 */
    rf_init(&before,1); CHECK(rf_configure(&before,1,3,7530));
    struct HblMechanicalSync sample={HBL_MECH_MAGIC,1,1,HBL_MECH_CLOCK|(8u<<8),0,0,123,1,1,0,3};
    CHECK(mechanical_rf_accept(&before,&sample,1000000,1000300,1));
    after=before;
    event.deadline_us=after.deadline_us; hbl_timing_push(&ring,&event);
    CHECK(memcmp(&before,&after,sizeof(before))==0 && after.deadline_us==1007530);
    CHECK(rf_due(&before,1007530)==rf_due(&after,1007530));
    CHECK(memcmp(&before,&after,sizeof(before))==0);
    puts("timing-ring-wrap-and-no-compensation-passed");
    return 0;
}
