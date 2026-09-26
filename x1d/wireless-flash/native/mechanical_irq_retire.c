/* 在 AppsMessaging 任务且已持有资源互斥量时撤销四个固定入口。
 * 不覆盖自己的代码；下一条由原厂处理的拒绝回复构成任务返回边界。
 */
#include <stdint.h>
void mechanical_irq_reset_call_guard(void);
void mechanical_irq_download_call_guard(void);
void mechanical_irq_ready_branch_guard(void);
void mechanical_irq_stage_message(const uint8_t *);
#define OLD_BL(a,b) (0xeb000000u|((((b)-(a)-8u)>>2)&0xffffffu))
struct hook { uint32_t address,original,target,link; };
__attribute__((section(".rodata.stage_retire")))
static const struct hook hooks[4]={
 {0x22b910u,OLD_BL(0x22b910u,0x22b4fcu),(uintptr_t)mechanical_irq_reset_call_guard,0xeb000000u},
 {0x22ceb8u,OLD_BL(0x22ceb8u,0x22b800u),(uintptr_t)mechanical_irq_download_call_guard,0xeb000000u},
 {0x22cd90u,0xe30b32e4u,(uintptr_t)mechanical_irq_ready_branch_guard,0xea000000u},
 {0x1e2264u,OLD_BL(0x1e2264u,0x1e1964u),(uintptr_t)mechanical_irq_stage_message,0xeb000000u}
};

__attribute__((section(".text.stage_retire")))
uint32_t mechanical_irq_stage_retire(void) {
    for(unsigned i=0;i<4;i++) {
        uint32_t value=hooks[i].link|(((hooks[i].target-hooks[i].address-8u)>>2)&0xffffffu);
        if(*(volatile uint32_t *)(uintptr_t)hooks[i].address!=value) return 24;
    }
    for(unsigned i=0;i<4;i++) {
        *(volatile uint32_t *)(uintptr_t)hooks[i].address=hooks[i].original;
        uint32_t line=hooks[i].address&~31u;
        ((void (*)(uint32_t,uint32_t))0x10a270u)(line,32);
        ((void (*)(uint32_t,uint32_t))0x10a354u)(line,32);
    }
    __asm__ volatile("dsb sy\nisb sy":::"memory");
    return 0;
}
