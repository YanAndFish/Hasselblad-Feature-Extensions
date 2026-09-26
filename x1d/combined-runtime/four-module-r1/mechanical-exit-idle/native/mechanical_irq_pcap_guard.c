/* 官方 X1D 1.25.0 的复位握手候选：只供离线原始指令回放。
 * 不能单独部署；高层资源流程仍须处理失败，不得直接继续恢复桥接。
 */
#include <stdint.h>
#define REG ((volatile uint32_t *)0xf8007000u)
#define TICK ((uint32_t (*)(void))0x22a924u)
#define SLEEP ((void (*)(uint32_t))0x187bd8u)
/* 0 未执行，1 开始，2 下载成功，3 下载失败；不等于资源恢复成功。 */
volatile uint32_t mechanical_irq_download_state=0xffffffffu;
/* 只有专用任务持有原资源锁并调用 RELOAD 时为 1；普通唤醒保持原代码。 */
volatile uint32_t mechanical_irq_guard_active __attribute__((section(".data")))=0;

static int wait_register(uint32_t offset,uint32_t mask,uint32_t expected) {
    uint32_t start=TICK();
    /* 每次未就绪让出一个原厂调度 tick，避免紧循环次数先于时限耗尽。
     * 调度必须正常；这不是调度器失效时的独立硬件看门狗。 */
    for(unsigned i=0;i<401;i++) {
        if((REG[offset/4]&mask)==expected) return 1;
        if((uint32_t)(TICK()-start)>=400u) break;
        SLEEP(1);
    }
    return 0;
}

uint32_t mechanical_irq_bounded_reset(void) {
    uint32_t cpsr;
    __asm__ volatile("mrs %0,cpsr":"=r"(cpsr));
    if((cpsr&0x1fu)!=0x13u && (cpsr&0x1fu)!=0x1fu) return 10;
    if(cpsr&0x80u) return 10;
    uint32_t instance=*(volatile uint32_t *)0x6db2e4u;
    if(instance<0x6b0000u || instance>0x6efff4u || (instance&3u)) return 10;
    if(*(volatile uint32_t *)(uintptr_t)(instance+4)!=0xf8007000u) return 10;
    if(*(volatile uint32_t *)(uintptr_t)(instance+8)!=0x11111111u) return 10;
    uint32_t control=REG[0];
    REG[0]=control|0x40000000u;
    if(control&0x1000u) SLEEP(5);
    REG[0]=control&~0x40000000u;
    if(control&0x1000u) SLEEP(5);
    if(!wait_register(0x14u,0x10u,0)) return 11;
    REG[0]=control|0x40000000u;
    if(!wait_register(0x14u,0x10u,0x10u)) return 12;
    if(!wait_register(0x14u,0x80000000u,0)) return 13;
    return 0;
}

uint32_t mechanical_irq_bounded_ready(void) {
    return wait_register(0x80u,0x100u,0x100u) ? 0u:14u;
}
