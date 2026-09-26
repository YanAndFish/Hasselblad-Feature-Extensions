/* 固定 X1D 1.25.0 FARM；普通 SUC 冲洗启动独立编号。无线一次资格由界面/worker消费。 */
#include "mechanical_sync_wire.h"
struct HblMechanicalRecord {
    uint32_t magic, armed, stage, sequence;
    struct HblMechanicalSync sample;
    uint32_t queued, dropped, seen, previous, packet[72];
};
_Static_assert(sizeof(struct HblMechanicalRecord)==364,"record ABI");
static uint32_t read32(uint32_t address) { return *(volatile const uint32_t *)(uintptr_t)address; }
static int valid(volatile struct HblMechanicalRecord *r) {
    return r && !((uintptr_t)r&3) && r->magic==HBL_MECH_MAGIC;
}
static void increment(volatile uint32_t *v) { if (*v!=UINT32_MAX) ++*v; }
/* 任意新的 SENSORIF 启动清零先关闭旧采集窗口，避免跨请求拼接。 */
__attribute__((used,visibility("default")))
void mechanical_sync_cancel_old(volatile struct HblMechanicalRecord *r) {
    if (valid(r) && r->stage>=2) r->stage=0;
}
__attribute__((used,visibility("default")))
uint32_t mechanical_sync_begin(volatile struct HblMechanicalRecord *r,uint32_t mode) {
    if (!valid(r) || r->armed!=1 || mode>1) return 0;
    r->stage=0;
    if (r->sequence==UINT32_MAX) { r->armed=0; return 0; }
    ++r->sequence;
    r->sample.magic=HBL_MECH_MAGIC; r->sample.version=1; r->sample.trial=r->sequence;
    r->sample.clear_flags=r->sample.cleared_status=r->sample.sync_status=0;
    r->sample.timer_low=r->sample.timer_high=r->sample.timer_control=0;
    r->sample.mode=mode; r->sample.source=3; r->seen=r->previous=0; r->stage=1;
    return 0x40;
}
__attribute__((used,visibility("default")))
void mechanical_sync_cleared(volatile struct HblMechanicalRecord *r) {
    if (!valid(r) || r->armed!=1 || r->stage!=1) return;
    const uint32_t status=read32(0x42000014);
    r->sample.cleared_status=status;
    r->sample.clear_flags=(!(status&HBL_MECH_A) ? 1u:0u) | (!(status&HBL_MECH_B) ? 2u:0u);
    r->previous=status;
    r->stage=2;
}
__attribute__((used,visibility("default")))
void mechanical_sync_sample(volatile struct HblMechanicalRecord *r,uint32_t status,uint32_t final) {
    if (!valid(r) || r->armed!=1 || (r->stage!=2 && r->stage!=3)) return;
    const uint32_t first=r->stage==2,prior=r->previous,rising=status&~prior,falling=prior&~status;
    r->stage=3;
    r->previous=status;
    uint32_t events=0;
    if ((r->sample.clear_flags&1) && (status&HBL_MECH_A)) events|=1;
    if ((r->sample.clear_flags&2) && (status&HBL_MECH_B)) events|=2;
    if (rising&4) events|=4;
    if (falling&1) events|=8;
    if (rising&2) events|=16;
    if (rising&8) events|=32;
    if ((r->seen&8) && (rising&1)) events|=64;
    events&=~r->seen;
    r->seen|=events;
    const uint32_t done=final || (events&64);
    if (done) r->stage=0;
    if (!events && !first && !done) return;
    r->sample.sync_status=status;
    r->sample.clear_flags=(r->sample.clear_flags&3) | (events<<8) | (done ? HBL_MECH_DONE:0);
    r->sample.timer_low=r->sample.timer_high=0;
    const uint32_t timer=0xf8f00200,control=read32(timer+8);
    r->sample.timer_control=control;
    if (control&1) for (unsigned i=0;i<4;++i) {
        const uint32_t hi=read32(timer+4),lo=read32(timer);
        if (hi==read32(timer+4)) {
            if (control==read32(timer+8)) {
                r->sample.timer_low=lo; r->sample.timer_high=hi; r->sample.clear_flags|=HBL_MECH_CLOCK;
            }
            break;
        }
    }
    for (unsigned i=0;i<72;++i) r->packet[i]=0;
    r->packet[0]=0x05010009;
    const volatile uint32_t *fields=(const volatile uint32_t *)&r->sample;
    for (unsigned i=0;i<11;++i) r->packet[i+1]=fields[i];
    __asm__ volatile("dmb sy" ::: "memory");
    const uint32_t queue=read32(0x6c4df4);
    if (!queue || (queue&3)) { increment(&r->dropped); return; }
    typedef int (*QueueSend)(uint32_t,const void *,uint32_t,uint32_t);
    if (((QueueSend)(uintptr_t)0x186500)(queue,(const void *)r->packet,0,0)==1) increment(&r->queued);
    else increment(&r->dropped);
}
__attribute__((used,visibility("default")))
void mechanical_sync_observe(volatile struct HblMechanicalRecord *r) {
    if (!valid(r) || r->armed!=1 || r->stage!=2) return;
    mechanical_sync_sample(r,read32(0x42000014),0);
}
