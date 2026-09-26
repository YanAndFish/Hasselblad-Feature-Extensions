/* 官方 X1D 1.25.0 临时 AppsMessaging 任务入口；当前仅离线构建。
 * 0xa0 检查、0xa1 装载候选、0xa2 只恢复缓存、0xa3 撤销入口；原厂均拒绝。
 * 不接收任意指针、函数或寄存器值。失败后不自动再次配置硬件。
 */
#include <stdint.h>

uint32_t mechanical_irq_cache_classify(const volatile uint32_t *,uint32_t);
uint32_t mechanical_irq_cache_change(volatile uint32_t *,uint32_t,uint32_t,uint32_t);
extern volatile uint32_t mechanical_irq_download_state;
extern volatile uint32_t mechanical_irq_guard_active;
uint32_t mechanical_irq_stage_retire(void);

struct stage_record { uint32_t magic,command,result,cache_state,configured,fault,power_state; };
volatile struct stage_record mechanical_irq_stage_record={0x32504749u,0,0,3,0,0,2};
#define IMAGE ((volatile uint32_t *)0x02129040u)
#define BYTES 5979936u
#define LOCK ((uint32_t (*)(uint32_t,uint32_t,uint32_t))0x22a9a4u)
#define UNLOCK ((void (*)(void))0x22aa98u)
#define RELOAD ((uint32_t (*)(void))0x22cc4cu)
#define ORIGINAL ((void (*)(const uint8_t *))0x1e1964u)
#define HEADER ((void (*)(const uint8_t *,uint8_t *,uint32_t))0x1e0a50u)
#define SEND ((void (*)(uint8_t *))0x1e80d0u)

/* 原厂任务调度中静默等候；不持有资源锁，不由电脑轮询保持链路活动。
 * 只调用正常关闭入口，忙时退出；不改任何资源状态或电源标志。 */
__attribute__((section(".text.stage_idle"),noinline))
uint32_t mechanical_irq_wait_for_close(void) {
    if(*(volatile uint32_t *)0x6badecu) return 10;
    ((void (*)(uint32_t))0x187bd8u)(600);
    if(*(volatile uint8_t *)0x6bb46cu) return 13;
    return ((uint32_t (*)(void))0x22e3d4u)()?25u:0u;
}

static uint32_t operate(uint32_t command) {
    uint32_t cpsr;
    __asm__ volatile("mrs %0,cpsr":"=r"(cpsr));
    if(((cpsr&31u)!=19u && (cpsr&31u)!=31u) || (cpsr&0x80u)) return 10;
    if(*(volatile uint32_t *)0x02129004u!=BYTES || *(volatile uint32_t *)0x02129008u!=(uintptr_t)IMAGE) return 11;
    /* 原厂这六节为非缓存保留映射；拒绝映射改变，不猜测 D-cache 状态。 */
    for(uint32_t i=0x21;i<=0x26;i++)
        if(((volatile uint32_t *)0x2b4000u)[i]!=(i<<20|0xc02u)) return 12;
    if(*(volatile uint8_t *)0x6bb46cu || !*(volatile uint32_t *)0x6db2c4u) return 13;
    if(command==0xa1 && (mechanical_irq_stage_record.fault || mechanical_irq_stage_record.configured)) return 17;
    if(command==0xa1 && *(volatile uint8_t *)0x2b20ccu) {
        uint32_t result=mechanical_irq_wait_for_close();
        if(result) return result;
    }
    if(!LOCK(0,0,0)) return 14;
    if(*(volatile uint8_t *)0x6bb46cu) { UNLOCK();return 13; }
    if(command==0xa3) { uint32_t r=mechanical_irq_stage_retire();UNLOCK();return r; }
    if(command==0xa1 && *(volatile uint8_t *)0x2b20ccu) { UNLOCK();return 23; }
    uint32_t state=mechanical_irq_cache_classify(IMAGE,BYTES),result=0;
    mechanical_irq_stage_record.cache_state=state;
    if(state==3) result=15;
    else if(command==0xa0) { /* 只分类；不复位或下载。 */ }
    else if(command==0xa2) {
        result=mechanical_irq_cache_change(IMAGE,BYTES,2,253)?16u:0u;
        __asm__ volatile("dsb sy":::"memory");
        if(!result) mechanical_irq_stage_record.cache_state=0;
    } else if(state!=0) result=17;
    else {
        result=mechanical_irq_cache_change(IMAGE,BYTES,1,253)?18u:0u;
        __asm__ volatile("dsb sy":::"memory");
        if(!result) {
            mechanical_irq_download_state=0;
            if(*(volatile uint8_t *)0x6bb46cu) result=13;
            else {
                mechanical_irq_guard_active=1;
                result=RELOAD()?19u:0u;
                mechanical_irq_guard_active=0;
            }
            if(!result && mechanical_irq_download_state!=2) result=22;
            mechanical_irq_stage_record.configured=result?0u:1u;
            mechanical_irq_stage_record.fault=(result && mechanical_irq_download_state)?1u:0u;
        }
        /* 成功保留候选缓存，供原厂后续待机恢复使用；正常重启重建原厂缓存。
         * 失败只回滚 RAM，不宣称恢复 PL；fault 阻止自动重试。 */
        if(result) {
            if(mechanical_irq_cache_change(IMAGE,BYTES,2,253)) { result=20;mechanical_irq_stage_record.fault=1; }
            else mechanical_irq_stage_record.cache_state=0;
        } else mechanical_irq_stage_record.cache_state=1;
        __asm__ volatile("dsb sy":::"memory");
    }
    UNLOCK();return result;
}

void mechanical_irq_stage_message(const uint8_t *message) {
    if(message!=(const uint8_t *)0x6c37f4u) return;
    uint32_t command=message[4];
    if(command<0xa0 || command>0xa3) { ORIGINAL(message);return; }
    uint8_t reply[8]={0};HEADER(message,reply,0x21c);
    uint32_t result=21;
    if(message[0]==0x1b && message[1]==2 && message[2]==8 && message[3]==1) {
        mechanical_irq_stage_record.command=command;
        result=operate(command);
        mechanical_irq_stage_record.result=result;
        mechanical_irq_stage_record.power_state=*(volatile uint8_t *)0x2b20ccu;
    }
    reply[4]=result?1:0;SEND(reply);
}
