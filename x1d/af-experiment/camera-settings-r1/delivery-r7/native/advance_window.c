#include "af_policy.h"
#define R8(a) (*(volatile unsigned char *)(a))
#define R16(a) (*(volatile unsigned short *)(a))
#define R32(a) (*(volatile u32 *)(a))
/* 1.25.0 WaitForSingleObject adapter 11d704 converts milliseconds *1000/1000
   to 188624 ticks. This is firmware scheduling time, never exposure time. */
struct Window {volatile u32 sequence,generation,count,tick,period,intervals,sampled_generation;};
__attribute__((section(".data.state"),used)) struct Window af_window={0};
static u32 consumed_generation,consumed_count;
void af_window_reset(u32 generation){
    /* AF_SERVICE owns sample data; generation change is detected there. */
    __atomic_store_n(&af_window.generation,generation,__ATOMIC_RELEASE);
}
void af_window_sample(u32 count){
    u32 generation=af_window.generation,now=R32(0x6badd0);
    if(af_window.sampled_generation==generation && count==af_window.count)return;
    af_window.sequence++;__asm__ volatile("dmb ish":::"memory");
    if(af_window.sampled_generation!=generation || count!=af_window.count+1){
        af_window.intervals=0;af_window.period=0;af_window.sampled_generation=generation;
    }else{
        u32 delta=now-af_window.tick;
        if(delta && delta<=1000){af_window.period=delta;af_window.intervals++;}
        else{af_window.period=0;af_window.intervals=0;}
    }
    af_window.tick=now;af_window.count=count;
    __asm__ volatile("dmb ish":::"memory");af_window.sequence++;
}
static int advance(void){
    u32 ms=af_current_advance();if(!ms || ms>1000 || R8(0x6bb46c)!=4)return 0;
    u32 seq=af_window.sequence,generation=af_window.generation,count=af_window.count;
    __asm__ volatile("dmb ish":::"memory");
    u32 period=af_window.period,intervals=af_window.intervals;
    if(seq&1 || af_window.sampled_generation!=generation || !period || intervals<2 || count<4 || count>500 || R16(0x6bc954)!=count)return 0;
    if(consumed_generation==generation && consumed_count==count)return 0;
    u32 falls=0,previous=R32(0x6bb5cc+(count-4)*4);
    for(u32 i=count-3;i<count;i++){
        u32 current=R32(0x6bb5cc+i*4);
        if(current<previous)falls++;else if(current>previous)falls=0;
        previous=current;
    }
    /* Three decreases already satisfy the untouched factory function. The
       advance requires an observed decrease, never an invented peak/position. */
    if(!falls || falls>=3 || (3-falls)*period>ms)return 0;
    __asm__ volatile("dmb ish":::"memory");
    if(seq!=af_window.sequence || generation!=af_window.generation ||
       R16(0x6bc954)!=count || R8(0x6bb46c)!=4 || af_current_advance()!=ms)return 0;
    u32 first=R8(0x6bb59c),second=R8(0x6bb59d);
    if(!first && !second)return 0;
    consumed_generation=generation;consumed_count=count;
    ((void (*)(u32))0x1a4890)(0x40);
    if(first)R8(0x6bb59d)=1;else R8(0x6bb59c)=1;
    return 1;
}
extern void af_native_peak(void);
void af_peak_window(void){if(!advance())af_native_peak();}
