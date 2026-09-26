/* 固定 prepared-wltest.bin 的离线候选：开启时准备，触发时启动。
 * 地址仅适用于本项目哈希绑定的 BCM4356 WLTEST 输入；尚未实机验证。
 * 不改变波形、增益、原厂延时参数；每次发射结束后重新准备下一次。
 */
#include <stdint.h>

#define FN(addr, type) ((type)(uintptr_t)((addr) | 1u))
#define STATE ((volatile uint32_t *)0x2147e0u)
#define HASH 0x0e77be41u
#define READY_MAGIC 0x48575031u

typedef struct {
    uint32_t magic, owner, regs, acquired, ready;
    uint16_t control, start, end, phy471;
} PreparedHardware;
#define HW ((volatile PreparedHardware *)0x217f00u)

typedef void (*PiVoid)(uintptr_t);
typedef void (*PiMode)(uintptr_t, unsigned);
typedef unsigned (*PiRead)(uintptr_t, unsigned);
typedef void (*PiWrite)(uintptr_t, unsigned, unsigned);
typedef void (*PiSamples)(uintptr_t, unsigned, unsigned, unsigned, unsigned, unsigned);
typedef unsigned (*PiResult)(uintptr_t);
typedef void (*Delay)(unsigned);

static uint16_t r16(uintptr_t address) { return *(volatile uint16_t *)address; }
static uint32_t r32(uintptr_t address) { return *(volatile uint32_t *)address; }
static void w16(uintptr_t address, uint16_t value) { *(volatile uint16_t *)address=value; }

static unsigned base_ready(uintptr_t pi, uintptr_t regs) {
    if (STATE[4]!=1 || STATE[0]!=1 || STATE[2]!=1 || STATE[1]!=HASH) return 2;
    if (r16(pi+0x10e)!=0x1002) return 4;
    if (r32(regs+0x120)&1u) return 5;
    if (r16(regs+0x538)!=0) return 6;
    if (r16(regs+0x492)!=2) return 7;
    return 0;
}

static void clean_hardware(void) {
    if (HW->magic!=READY_MAGIC) return;
    HW->ready=0;
    if (HW->acquired) {
        uintptr_t pi=HW->owner, regs=HW->regs;
        w16(regs+0x492,HW->control);
        FN(0x1bb210,PiVoid)(pi);
        FN(0x1c6224,PiWrite)(pi,0x471,HW->phy471);
        FN(0x1bb31c,PiMode)(pi,0);
        w16(regs+0x55a,HW->start);
        w16(regs+0x55c,HW->end);
        w16(regs+0x492,HW->control);
        HW->acquired=0;
    }
    HW->magic=0;
}

__attribute__((used)) unsigned hbl_hw_prepare(uintptr_t pi) {
    uintptr_t regs=r32(pi+0x100);
    unsigned error=base_ready(pi,regs);
    if (HW->magic==READY_MAGIC && HW->owner!=pi) return 9;
    if (error) { clean_hardware(); return error; }
    if (HW->magic==READY_MAGIC && HW->ready) {
        if (HW->regs==regs && r16(regs+0x55a)==0x9000 && r16(regs+0x55c)==0xff00) return 1;
        clean_hardware(); return 11;
    }
    clean_hardware();
    HW->owner=pi; HW->regs=regs;
    HW->control=r16(regs+0x492);
    HW->start=r16(regs+0x55a); HW->end=r16(regs+0x55c);
    HW->phy471=(uint16_t)FN(0x1c620e,PiRead)(pi,0x471);
    HW->acquired=0; HW->ready=0; HW->magic=READY_MAGIC;
    FN(0x1bb31c,PiMode)(pi,1);
    HW->acquired=1;
    w16(regs+0x492,HW->control);
    w16(regs+0x55a,0x9000); w16(regs+0x55c,0xff00);
    /* 与已装第一版相同的准备函数，包含其原有延时和完成状态查询。
     * 此调用没有新增的 D11 波形启动写入；实际待发状态可保持性仍待实测。
     */
    FN(0x1bb3d6,PiSamples)(pi,0x6f00,1,0,0,1);
    if (FN(0x1c620e,PiRead)(pi,0x403)&1u) {
        clean_hardware(); return 8;
    }
    HW->ready=1;
    return 1;
}

__attribute__((used)) unsigned hbl_hw_fire(uintptr_t pi) {
    if (HW->magic!=READY_MAGIC || !HW->ready || HW->owner!=pi) return 9;
    uintptr_t regs=HW->regs;
    if (r32(pi+0x100)!=regs || r16(regs+0x55a)!=0x9000 || r16(regs+0x55c)!=0xff00) {
        clean_hardware(); return 11;
    }
    unsigned error=base_ready(pi,regs);
    if (error) { clean_hardware(); return error; }
    HW->ready=0;
    /* 最后确认硬件仍就绪；等待函数只在准备或启动后调用。 */
    if (FN(0x1c620e,PiRead)(pi,0x403)&1u) { clean_hardware(); return 8; }
    uint32_t flags;
    __asm__ volatile("mrs %0, cpsr\n\tcpsid if" : "=r"(flags) :: "memory");
    w16(regs+0x492,0x1802);
    FN(0x8710,Delay)(500);
    w16(regs+0x492,HW->control);
    __asm__ volatile("msr cpsr_c, %0" :: "r"(flags) : "memory");
    clean_hardware();
    /* 完成本次后立即准备下一次；失败也不重发已经提交的波形。 */
    return hbl_hw_prepare(pi)==1 ? 1 : 10;
}

__attribute__((used)) unsigned hbl_hw_release(uintptr_t pi) {
    if (HW->magic==READY_MAGIC && HW->owner!=pi) return 9;
    clean_hardware();
    return FN(0x215fa0,PiResult)(pi);
}
