/* 固定官方 X1D 1.25.0；两个独立 PL 中断。仅构建离线候选，尚无装载入口。
 * FPGA：IRQF2P14=启动保持；IRQF2P15=反相后的空闲状态。
 * FARM：90/91，同优先级、CPU0；不主动触发中断，不改变传感器控制。
 */
#include "mechanical_irq_capture.h"
#define FN(address,type) ((type)(uintptr_t)(address))
#define GIC_ENABLE UINT32_C(0xf8f01108)
#define GIC_DISABLE UINT32_C(0xf8f01188)
#define GIC_PENDING UINT32_C(0xf8f01208)
#define GIC_CLEAR UINT32_C(0xf8f01288)
#define GIC_ACTIVE UINT32_C(0xf8f01308)
#define GIC_PRIORITY UINT32_C(0xf8f01458)
#define GIC_TARGETS UINT32_C(0xf8f01858)
#define GIC_CONFIG UINT32_C(0xf8f01c14)
#define HANDLER90 UINT32_C(0x002a52cc)
#define HANDLER91 UINT32_C(0x002a52d4)
static uint32_t read32(uint32_t a) { return *(volatile const uint32_t *)(uintptr_t)a; }
static void write32(uint32_t a,uint32_t v) { *(volatile uint32_t *)(uintptr_t)a=v; }
static uint32_t lock(void) {
    uint32_t value;
    __asm__ volatile("mrs %0,cpsr\n cpsid i\n dsb sy\n isb sy" : "=r"(value) :: "memory");
    return value;
}
static void unlock(uint32_t value) {
    __asm__ volatile("dmb sy" ::: "memory");
    if (!(value&0x80)) __asm__ volatile("cpsie i\n isb sy" ::: "memory");
}
static void barrier(void) { __asm__ volatile("dsb sy\n isb sy" ::: "memory"); }
static int valid(volatile struct HblMechanicalIrqRecord *r) {
    return r && !((uintptr_t)r&3) && r->magic==HBL_MECH_IRQ_MAGIC;
}
static int ready(volatile struct HblMechanicalIrqRecord *r) {
    return valid(r) && r->configured==HBL_MECH_IRQ_MAGIC;
}
static void increment(volatile uint32_t *v) { if (*v!=UINT32_MAX) ++*v; }
void mechanical_irq_hold(void *arg);
void mechanical_irq_idle(void *arg);

/* 仅在处理器初始空闲、两个槽仍为原厂默认处理器、未启用/挂起/活动时配置。
 * 恢复信息保存在自有记录；不调用可能等待互斥量的平台注册包装。
 */
__attribute__((used,visibility("default")))
unsigned mechanical_irq_setup(volatile struct HblMechanicalIrqRecord *r) {
    if (!valid(r) || r->armed || r->stage || r->configured) return 0;
    uint32_t cpu; __asm__ volatile("mrc p15,0,%0,c0,c0,5" : "=r"(cpu));
    if (cpu&0xff) return 0;
    const uint32_t saved=lock();
    if (read32(0x2ad78c)!=0x2a4ffc || read32(0x6da728)!=0x2a4ff0 ||
        read32(0x6da72c)!=0x11111111 ||
        read32(HANDLER90)!=0x109304 || read32(HANDLER90+4)!=0x6da728 ||
        read32(HANDLER91)!=0x109304 || read32(HANDLER91+4)!=0x6da728 ||
        ((read32(GIC_ENABLE)|read32(GIC_PENDING)|read32(GIC_ACTIVE))&HBL_MECH_IRQ_BITS) ||
        (read32(0xf8f00108)&7)>2) { unlock(saved); return 0; }
    r->priority=read32(GIC_PRIORITY)&0xffff0000;
    r->targets=read32(GIC_TARGETS)&0xffff0000;
    r->config=read32(GIC_CONFIG)&0x00f00000;
    r->handler90=read32(HANDLER90); r->argument90=read32(HANDLER90+4);
    r->handler91=read32(HANDLER91); r->argument91=read32(HANDLER91+4);
    write32(GIC_PRIORITY,(read32(GIC_PRIORITY)&0x0000ffff)|0xa0a00000);
    write32(GIC_TARGETS,(read32(GIC_TARGETS)&0x0000ffff)|0x01010000);
    write32(GIC_CONFIG,(read32(GIC_CONFIG)&~0x00f00000)|0x00a00000);
    write32(HANDLER90+4,(uint32_t)(uintptr_t)r);
    write32(HANDLER91+4,(uint32_t)(uintptr_t)r);
    __asm__ volatile("dmb sy" ::: "memory");
    write32(HANDLER90,(uint32_t)(uintptr_t)mechanical_irq_hold);
    write32(HANDLER91,(uint32_t)(uintptr_t)mechanical_irq_idle);
    r->configured=HBL_MECH_IRQ_MAGIC;
    barrier(); unlock(saved); return 1;
}

__attribute__((used,visibility("default")))
unsigned mechanical_irq_restore(volatile struct HblMechanicalIrqRecord *r) {
    if (!ready(r) || r->armed || r->stage) return 0;
    const uint32_t saved=lock();
    if ((read32(GIC_ACTIVE)&HBL_MECH_IRQ_BITS) ||
        read32(HANDLER90)!=(uint32_t)(uintptr_t)mechanical_irq_hold ||
        read32(HANDLER91)!=(uint32_t)(uintptr_t)mechanical_irq_idle ||
        read32(HANDLER90+4)!=(uint32_t)(uintptr_t)r || read32(HANDLER91+4)!=(uint32_t)(uintptr_t)r) {
        unlock(saved); return 0;
    }
    write32(GIC_DISABLE,HBL_MECH_IRQ_BITS); barrier();
    write32(GIC_CLEAR,HBL_MECH_IRQ_BITS);
    write32(HANDLER90,r->handler90); write32(HANDLER90+4,r->argument90);
    write32(HANDLER91,r->handler91); write32(HANDLER91+4,r->argument91);
    write32(GIC_PRIORITY,(read32(GIC_PRIORITY)&0xffff)|r->priority);
    write32(GIC_TARGETS,(read32(GIC_TARGETS)&0xffff)|r->targets);
    write32(GIC_CONFIG,(read32(GIC_CONFIG)&~0x00f00000)|r->config);
    r->configured=0; barrier(); unlock(saved); return 1;
}

static void stamp(struct HblMechanicalSync *sample) {
    const uint32_t base=0xf8f00200, control=read32(base+8);
    sample->timer_low=sample->timer_high=0; sample->timer_control=control;
    sample->clear_flags&=~HBL_MECH_CLOCK;
    if (control&1) for (unsigned i=0;i<4;++i) {
        const uint32_t high=read32(base+4),low=read32(base);
        if (high==read32(base+4)) {
            if (control==read32(base+8)) {
                sample->timer_low=low; sample->timer_high=high;
                sample->clear_flags|=HBL_MECH_CLOCK;
            }
            break;
        }
    }
}

static void send(volatile struct HblMechanicalIrqRecord *r,const struct HblMechanicalSync *sample,unsigned irq) {
    uint32_t packet[72];
    for (unsigned i=0;i<72;++i) packet[i]=0;
    packet[0]=0x05010009;
    const uint32_t *fields=(const uint32_t *)sample;
    for (unsigned i=0;i<11;++i) packet[i+1]=fields[i];
    const uint32_t queue=read32(0x6c4df4);
    /* 原队列项大小在投递之前核对，避免结构变更导致越界复制。 */
    if (queue<0x100000 || queue>=0x10000000 || (queue&3) || read32(queue+0x40)!=287) {
        increment(&r->dropped); return;
    }
    int result;
    if (irq) {
        int wake=0;
        result=FN(0x1867e4,int (*)(uint32_t,const void *,int *,uint32_t))(queue,packet,&wake,0);
        if (wake) write32(0x6bacc4,1); /* 与原厂 AF 中断相同，由外层 IRQ 返回路径处理切换。 */
    } else result=FN(0x186500,int (*)(uint32_t,const void *,uint32_t,uint32_t))(queue,packet,0,0);
    const uint32_t saved=lock();
    if (result==1) increment(&r->queued); else increment(&r->dropped);
    unlock(saved);
}

__attribute__((used,visibility("default")))
void mechanical_sync_cancel_old(volatile struct HblMechanicalIrqRecord *r) {
    if (!ready(r)) return;
    const uint32_t saved=lock();
    write32(GIC_DISABLE,HBL_MECH_IRQ_BITS); barrier();
    write32(GIC_CLEAR,HBL_MECH_IRQ_BITS); r->stage=0;
    unlock(saved);
}
__attribute__((used,visibility("default")))
uint32_t mechanical_sync_begin(volatile struct HblMechanicalIrqRecord *r,uint32_t mode) {
    if (!ready(r) || r->armed!=1 || mode>1) return 0;
    const uint32_t saved=lock();
    if (r->sequence==UINT32_MAX) { r->armed=0; unlock(saved); return 0; }
    ++r->sequence; r->stage=1; r->seen=0; r->previous=0;
    r->sample.magic=HBL_MECH_MAGIC; r->sample.version=2; r->sample.trial=r->sequence;
    r->sample.clear_flags=r->sample.cleared_status=r->sample.sync_status=0;
    r->sample.timer_low=r->sample.timer_high=r->sample.timer_control=0;
    r->sample.mode=mode; r->sample.source=3;
    unlock(saved); return 0x40;
}
__attribute__((used,visibility("default")))
void mechanical_sync_cleared(volatile struct HblMechanicalIrqRecord *r) {
    if (!ready(r) || r->armed!=1 || r->stage!=1) return;
    const uint32_t saved=lock(), status=read32(0x42000014);
    r->sample.cleared_status=status; r->previous=status;
    if ((status&5)!=1) { r->stage=0; increment(&r->dropped); unlock(saved); return; }
    write32(GIC_CLEAR,HBL_MECH_IRQ_BITS);
    r->stage=2; __asm__ volatile("dmb sy" ::: "memory");
    write32(GIC_ENABLE,HBL_MECH_IRQ_BITS); barrier(); unlock(saved);
}
__attribute__((used,visibility("default")))
void mechanical_sync_observe(volatile struct HblMechanicalIrqRecord *r) { (void)r; }

static void event(volatile struct HblMechanicalIrqRecord *r,unsigned source) {
    if (!ready(r)) return;
    const uint32_t saved=lock(), mask=1u<<(source+24);
    write32(GIC_DISABLE,mask); write32(GIC_CLEAR,mask); barrier();
    if (r->armed!=1 || (r->stage!=2 && r->stage!=3) || (r->seen&(1u<<source))) {
        unlock(saved); return;
    }
    r->seen|=1u<<source; r->stage=3;
    struct HblMechanicalSync sample;
    const volatile uint32_t *from=(const volatile uint32_t *)&r->sample;
    uint32_t *to=(uint32_t *)&sample;
    for (unsigned i=0;i<11;++i) to[i]=from[i];
    sample.sync_status=read32(0x42000014);
    sample.clear_flags=1u<<(source+8);
    stamp(&sample);
    for (unsigned i=0;i<11;++i) ((volatile uint32_t *)&r->sample)[i]=to[i];
    unlock(saved);
    send(r,&sample,1);
}
__attribute__((used,visibility("default")))
void mechanical_irq_hold(void *arg) { event(arg,2); }
__attribute__((used,visibility("default")))
void mechanical_irq_idle(void *arg) { event(arg,3); }

/* 普通读取只用于结束/取消本次资格；不再从状态差分产生两种触发事件。 */
__attribute__((used,visibility("default")))
void mechanical_sync_sample(volatile struct HblMechanicalIrqRecord *r,uint32_t status,uint32_t final) {
    if (!ready(r) || r->armed!=1 || (r->stage!=2 && r->stage!=3)) return;
    const uint32_t saved=lock();
    const unsigned done=final || ((r->seen&8) && (status&1));
    r->previous=status;
    if (!done) { unlock(saved); return; }
    write32(GIC_DISABLE,HBL_MECH_IRQ_BITS); barrier();
    write32(GIC_CLEAR,HBL_MECH_IRQ_BITS); r->stage=0;
    struct HblMechanicalSync sample;
    const volatile uint32_t *from=(const volatile uint32_t *)&r->sample;
    uint32_t *to=(uint32_t *)&sample;
    for (unsigned i=0;i<11;++i) to[i]=from[i];
    sample.sync_status=status; sample.clear_flags=HBL_MECH_DONE;
    stamp(&sample); unlock(saved);
    send(r,&sample,0);
}
