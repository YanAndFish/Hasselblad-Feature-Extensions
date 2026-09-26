/* X1D 1.25.0 FARM：机械/电子共用入口和记录，保留原厂控制次序。 */
#include "mechanical_sync_wire.h"
#include "farm_sync_wire.h"
#define RECORD_MAGIC UINT32_C(0x31534648)
struct FormalSyncRecord {
    uint32_t magic, enabled, stage, sequence;
    union { struct HblMechanicalSync mech; struct HblFarmSync es; uint32_t words[11]; } sample;
    uint32_t queued, dropped, seen, previous, packet[72];
};
_Static_assert(sizeof(struct FormalSyncRecord)==364,"formal sync record ABI");
static uint32_t read32(uint32_t a) { return *(volatile const uint32_t *)(uintptr_t)a; }
static int valid(volatile struct FormalSyncRecord *r) {
    return r && !((uintptr_t)r&3) && r->magic==RECORD_MAGIC && r->enabled==1;
}
static void count(volatile uint32_t *v) { if (*v!=UINT32_MAX) ++*v; }
void formal_sync_cancel(volatile struct FormalSyncRecord *r) {
    if (valid(r)) r->stage=0;
}
/* kind=0 机械，kind=1 电子；只接受汇编中逐层校验过的原厂调用。 */
uint32_t formal_sync_begin(volatile struct FormalSyncRecord *r,uint32_t kind,uint32_t mode) {
    if (!valid(r) || kind>1 || mode>1 || (kind && mode)) return 0;
    r->stage=0;
    if (r->sequence==UINT32_MAX) { r->enabled=0; return 0; }
    ++r->sequence;
    for (unsigned i=0;i<11;++i) r->sample.words[i]=0;
    r->sample.words[0]=kind ? HBL_SYNC_MAGIC:HBL_MECH_MAGIC;
    r->sample.words[1]=kind ? 3:1;
    r->sample.words[2]=r->sequence;
    if (!kind) { r->sample.mech.mode=mode; r->sample.mech.source=3; }
    r->seen=r->previous=0; r->stage=1;
    return 0x40;
}
void formal_sync_cleared(volatile struct FormalSyncRecord *r) {
    if (!valid(r) || r->stage!=1) return;
    const uint32_t status=read32(0x42000014);
    r->sample.words[4]=status;
    if (r->sample.words[0]==HBL_MECH_MAGIC)
        r->sample.words[3]=(!(status&HBL_MECH_A) ? 1u:0u)|(!(status&HBL_MECH_B) ? 2u:0u);
    else r->sample.words[3]=!(status&HBL_SYNC_STATUS_BIT) ? HBL_SYNC_CLEAR:0;
    r->previous=status; r->stage=2;
}
/* 两种消息的时钟字段位置相同。每次重新采样，绝不沿用上一事件的时钟。 */
static void publish(volatile struct FormalSyncRecord *r) {
    r->sample.words[3]&=~4u;
    r->sample.words[6]=r->sample.words[7]=0;
    const uint32_t timer=0xf8f00200,control=read32(timer+8);
    r->sample.words[8]=control;
    if (control&1) for (unsigned i=0;i<4;++i) {
        const uint32_t hi=read32(timer+4),lo=read32(timer);
        if (hi==read32(timer+4)) {
            if (control==read32(timer+8)) {
                r->sample.words[6]=lo; r->sample.words[7]=hi; r->sample.words[3]|=4;
            }
            break;
        }
    }
    for (unsigned i=0;i<72;++i) r->packet[i]=0;
    r->packet[0]=0x05010009;
    for (unsigned i=0;i<11;++i) r->packet[i+1]=r->sample.words[i];
    __asm__ volatile("dmb sy" ::: "memory");
    const uint32_t queue=read32(0x6c4df4);
    if (!queue || (queue&3)) { count(&r->dropped); return; }
    typedef int (*QueueSend)(uint32_t,const void *,uint32_t,uint32_t);
    if (((QueueSend)(uintptr_t)0x186500)(queue,(const void *)r->packet,0,0)==1) count(&r->queued);
    else count(&r->dropped);
}
void formal_sync_mechanical(volatile struct FormalSyncRecord *r,uint32_t status,uint32_t final) {
    if (!valid(r) || r->sample.words[0]!=HBL_MECH_MAGIC || (r->stage!=2 && r->stage!=3)) return;
    const uint32_t first=r->stage==2,prior=r->previous,rising=status&~prior,falling=prior&~status;
    r->stage=3; r->previous=status;
    uint32_t events=0;
    if ((r->sample.mech.clear_flags&1) && (status&HBL_MECH_A)) events|=1;
    if ((r->sample.mech.clear_flags&2) && (status&HBL_MECH_B)) events|=2;
    if (rising&4) events|=4;
    if (falling&1) events|=8;
    if (rising&2) events|=16;
    if (rising&8) events|=32;
    if ((r->seen&8) && (rising&1)) events|=64;
    events&=~r->seen; r->seen|=events;
    const uint32_t done=final || (events&64);
    if (done) r->stage=0;
    if (!events && !first && !done) return;
    r->sample.mech.sync_status=status;
    r->sample.mech.clear_flags=(r->sample.mech.clear_flags&3)|(events<<8)|(done ? HBL_MECH_DONE:0);
    publish(r);
}
void formal_sync_started(volatile struct FormalSyncRecord *r) {
    if (valid(r) && r->sample.words[0]==HBL_MECH_MAGIC && r->stage==2)
        formal_sync_mechanical(r,read32(0x42000014),0);
}
void formal_sync_es_observe(volatile struct FormalSyncRecord *r,uint32_t low,uint32_t high) {
    if (!valid(r) || r->sample.words[0]!=HBL_SYNC_MAGIC || r->stage!=2) return;
    r->stage=3; r->sample.es.exposure_low=low; r->sample.es.exposure_high=high;
    r->sample.es.sync_status=read32(0x42000014);
    if ((r->sample.es.flags&HBL_SYNC_CLEAR) && (r->sample.es.sync_status&HBL_SYNC_STATUS_BIT))
        r->sample.es.flags|=HBL_SYNC_SEEN;
    publish(r);
    if (r->sample.es.flags!=7) r->stage=0;
}
void formal_sync_es_progress(volatile struct FormalSyncRecord *r,uint32_t value) {
    if (!valid(r) || r->sample.words[0]!=HBL_SYNC_MAGIC || (r->stage!=3 && r->stage!=4)) return;
    if (r->stage==4 && (r->sample.es.cleared_status>=100 || value<=r->sample.es.cleared_status)) return;
    r->sample.es.cleared_status=value; r->stage=4;
    r->sample.es.flags=0x103; r->sample.es.sync_status=read32(0x42000014); publish(r);
}
void formal_sync_es_stop(volatile struct FormalSyncRecord *r) {
    if (!valid(r) || r->sample.words[0]!=HBL_SYNC_MAGIC || r->stage!=4) return;
    r->stage=0; r->sample.es.flags=0x203;
    r->sample.es.sync_status=read32(0x42000014); publish(r);
}
