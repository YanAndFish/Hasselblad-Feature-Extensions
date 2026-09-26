/* 原厂采样旁路记录。不读取图像、不产生帧号、不把接收 tick 标成采样时间。 */
#include "native_capture.h"
#define R8(a) (*(volatile unsigned char *)(a))
#define R16(a) (*(volatile unsigned short *)(a))
#define RS16(a) (*(volatile signed short *)(a))
#define R32(a) (*(volatile u32 *)(a))
__attribute__((section(".data.capture"),used)) volatile struct NcCapture nc_capture={.magic=0x3150434e,.abi=2,.enabled=1};
/* 只验证已申请区域的取指与缓存可见性；不分配内存，不触发 AF。 */
void nc_execution_probe(volatile u32 *ack){
    if(ack==&nc_capture.reserved)__atomic_store_n(ack,0x314b4341,__ATOMIC_RELEASE);
}
/* stream=0 为 AF_SERVICE，1 为 CV IRQ，2 为 AF_SERVICE_SM。
   三个上下文各有独立的序号和存储，不能把两个原厂任务视为同一个写者。 */
static void record(u32 stream,u32 kind,u32 a,u32 b,u32 c,u32 d){
    volatile struct NcCapture *s=&nc_capture;
    u32 state=R8(0x6bb46c);
    if(s->enabled!=1 || (!state && kind!=NC_CYCLE) || state>8)return;
    volatile u32 *sequence=stream==1?&s->raw_sequence:(stream==2?&s->control_sequence:&s->af_sequence);
    u32 next=*sequence+1;
    /* 保留 commit=0 为未发布；即使计数溢出也不伪造有效记录。 */
    if(!next || next>=0x80000000u)return;
    volatile struct NcRecord *r=stream==1?&s->raw[(next-1)&63]:
        (stream==2?&s->control[(next-1)&31]:&s->af[(next-1)&127]);
    __atomic_store_n(&r->commit,(next<<1)|1,__ATOMIC_RELEASE);
    r->kind=kind;r->tick=R32(0x6badd0);r->generation=s->generation;r->state=state;
    r->data[0]=a;r->data[1]=b;r->data[2]=c;r->data[3]=d;
    __atomic_store_n(&r->commit,next<<1,__ATOMIC_RELEASE);
    __atomic_store_n(sequence,next,__ATOMIC_RELEASE);
}
void nc_raw(u32 a,u32 b,u32 mode){
    u32 video=R8(0x6c176c)|((u32)R8(0x6c1778)<<8)|((u32)R16(0x6c169a)<<16);
    record(1,NC_RAW,a,b,mode,video);
}
void nc_cv_fifo(u32 value,u32 index){
    if(index>=5){nc_capture.invalid++;return;}
    record(0,NC_CV_FIFO,value,index,R32(0x6bc980),R32(0x6bc984));
}
void nc_position_fifo(s32 position,u32 index,u32 lens_sequence){
    if(index>=5 || lens_sequence>=100){nc_capture.invalid++;return;}
    record(0,NC_POSITION_FIFO,(u32)position,index,lens_sequence,R32(0x6bc994));
}
extern void na_start_accepted(u32);
void nc_accepted(u32 count){
    if(!count || count>500){nc_capture.invalid++;return;}
    na_start_accepted(count);
    record(0,NC_ACCEPTED,count,(u32)RS16(0x6bbd9c+(count-1)*2),
           R32(0x6bb5cc+(count-1)*4),(R32(0x6bc980)&0xffff)|(R32(0x6bc994)<<16));
}
extern void na_cycle_reset(void);
extern s32 na_stage_speed(u32,s32);
void nc_cycle_reset(void){
    na_cycle_reset();nc_capture.generation++;
    record(2,NC_CYCLE,nc_capture.raw_sequence,nc_capture.af_sequence,0,0);
}
static void command(u32 stage,s32 requested){
    u32 started=R32(0x6badd0);s32 packet_argument=na_stage_speed(stage,requested);
    record(stage==0?0:2,NC_COMMAND,stage,(u32)requested,(u32)packet_argument,started);
}
void nc_probe_speed(s32 v){command(0,v);}
void nc_fast_speed(s32 v){command(1,v);}
void nc_fine_speed(s32 v){command(2,v);}

extern s32 na_resume_probe(s32);
void nc_probe_resume(s32 requested){
    u32 started=R32(0x6badd0);s32 argument=na_resume_probe(requested);
    record(2,NC_COMMAND,0,(u32)requested,(u32)argument,started);
}
