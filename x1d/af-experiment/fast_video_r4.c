/* 开发中的视频任务构件，已与R4离线链接，尚不可安装。
   FARM SHA-256 317841f6f4dff599cda8c83f2b4912f78534db20e7690d0b14b0cd5f1b8c39ca。 */
#include "fast_video_r4.h"
typedef unsigned short u16;
typedef unsigned char u8;
#define U fv_u32
#define V fast_video_state
#define R32(a) (*(volatile U *)(a))
#define R8(a) (*(volatile u8 *)(a))
#define NOW R32(0x6badd0)
#define CAMERA_STATE R8(0x6bb46c)
#define VIDEO_ACTIVE R8(0x6c176c)
#define VIDEO_MODE R8(0x6c1778)
#define VIDEO_CFG ((const u8 *)0x6c1690)
#define FAST __attribute__((used,noinline,section(".text.fastvideo")))
#define ARM __attribute__((used,noinline,target("arm"),section(".text.fastvideo")))
#define ENTRY __attribute__((naked,used,noinline,target("arm"),section(".text.fastvideo")))
__attribute__((used,section(".data.fast")))
struct FastVideoState V={.magic=0x46313630,.abi=1,.canary=0x30363146};
__attribute__((used,section(".data.fast")))
volatile U fast_video_begin_status=0x80000000u,fast_video_begin_generation=0;
static void barrier(void){__asm__ volatile("dmb ish" ::: "memory");}
ENTRY static void real_videooff(U kind){__asm__ volatile("push {fp,lr}\nldr pc,1f\n1:.word 0x1c9618");}
ENTRY static void real_videoon(U mode,U width,U height,U aux){__asm__ volatile("push {fp,lr}\nldr pc,1f\n1:.word 0x1c9938");}
ENTRY static U real_roi(void *roi){__asm__ volatile("push {fp,lr}\nldr pc,1f\n1:.word 0x1f0e70");}
ARM void fast_videooff(U kind){
    /* 本构件服务直接调用real_*，所有经补丁入口的调用都属于外部生命周期。 */
    V.external_epoch++;
    real_videooff(kind);
}
ARM void fast_videoon(U mode,U width,U height,U aux){
    V.external_epoch++;
    if(mode==5){V.observed_width=width;V.observed_height=height;}
    real_videoon(mode,width,height,aux);
}
ARM U fast_video_pipeline(const u8 *cfg,U pipeline,U width,U height,void *parameters){
    U applying=V.applying;
    if(applying && V.target==7 && cfg==VIDEO_CFG && cfg[1]==7) pipeline=2;
    U result=((U (*)(const u8 *,U,U,U,void *))0x201e44)(cfg,pipeline,width,height,parameters);
    if(applying){V.pipeline_calls++;V.pipeline_result=result;}
    return result;
}
ARM U fast_video_roi(void *roi){
    if(V.applying){
        U a=V.roi0;
        if(V.target==7)a=(a&0xffff0000u)|((a&65535)-158);
        ((U *)roi)[0]=a;((U *)roi)[1]=V.roi1;
    }
    return real_roi(roi);
}
ARM U fast_video_spi(U kind,U offset,U count,void *buffer,void *parameters){
    U applying=V.applying;
    if(applying && kind==2 && offset==0 && buffer==(void *)0x6db2e8)count=256;
    U result=((U (*)(U,U,U,void *,void *))0x234c64)(kind,offset,count,buffer,parameters);
    if(applying){V.spi_calls++;V.spi_result=result;V.spi_bytes=count;}
    return result;
}
ARM void fast_video_exposure(U mode,const u8 *cfg,void *exposure){
    /* 7的原厂路径固定最大曝光并查ISO表；AF短帧沿用5的测光/增益计算，
       仍由当前160配置的最大曝光约束，不改用户设置或绕过曝光钳制。 */
    if(V.applying && V.target==7 && mode==7 && cfg==VIDEO_CFG)mode=5;
    ((void (*)(U,const u8 *,void *))0x21d8b8)(mode,cfg,exposure);
}
__attribute__((used,noinline,section(".text.extra8")))
U fast_video_begin(U generation,U roi0,U roi1,U rate){
    fast_video_begin_generation=0;barrier();
    U reason=0;
    if(V.dirty || V.request!=V.ack)reason|=FV_GATE_BUSY;
    else V.session=0;
    if(V.enabled!=2)reason|=FV_GATE_DISABLED;
    if(V.need_recovery)reason|=FV_GATE_RECOVERY;
    if(CAMERA_STATE!=3)reason|=FV_GATE_AF_STATE;
    if(!VIDEO_ACTIVE)reason|=FV_GATE_INACTIVE;
    if(VIDEO_MODE!=5)reason|=FV_GATE_MODE;
    if(!generation)reason|=FV_GATE_GENERATION;
    if(!V.observed_width || !V.observed_height)reason|=FV_GATE_DIMENSIONS;
    if(R32(0x6c173c)>0x3f800000u)reason|=FV_GATE_GAIN;
    U y=roi0&65535,x=roi0>>16,w=roi1&65535,h=roi1>>16;
    if(!w || !h || x<4 || x+w>2744 || y<162 || y+h>306)reason|=FV_GATE_ROI;
    fast_video_begin_status=reason;barrier();fast_video_begin_generation=generation;
    if(reason)return 0;
    V.session=generation;V.session_epoch=V.external_epoch;
    V.width=V.observed_width;V.height=V.observed_height;
    V.roi0=roi0;V.roi1=roi1;V.full_rate=rate;return 1;
}
FAST U fast_video_request(U target){
    if(!V.session || V.need_recovery || V.request!=V.ack || (target!=5 && target!=7))return 0;
    V.target=target;V.request_epoch=V.session_epoch;V.result=FV_CONFIG;
    barrier();V.request++;return 1;
}
static FAST U request_current(void){
    return V.enabled==2 && V.session && !V.need_recovery &&
        V.request_epoch==V.external_epoch && CAMERA_STATE==3;
}
FAST void fast_video_service(void){
    U seq=V.request;if(seq==V.ack)return;barrier();
    U target=V.target,result=FV_SUPERSEDED;
    if(!request_current() ||
       (VIDEO_ACTIVE && VIDEO_MODE!=5 && VIDEO_MODE!=7) || (!VIDEO_ACTIVE && !V.dirty))goto done;
    V.applying=1;V.pipeline_calls=0;V.spi_calls=0;V.pipeline_result=FV_CONFIG;V.spi_result=FV_CONFIG;
    if(((U (*)(void))0x1f0b04)()!=0){result=FV_STOP_FAILED;goto applied;}
    if(!request_current())goto applied;
    V.dirty=1;
    real_videooff(0);
    if(VIDEO_ACTIVE){result=FV_STOP_FAILED;goto applied;}
    if(!request_current())goto applied;
    real_videoon(target,target==7?64:V.width,target==7?64:V.height,0);
    if(!request_current())goto applied;
    if(V.spi_calls && (V.spi_calls!=1 || V.spi_result || V.spi_bytes!=256)){result=FV_SENSOR_FAILED;goto applied;}
    if(!VIDEO_ACTIVE || VIDEO_MODE!=target){result=FV_APPLY_FAILED;goto applied;}
    if(V.pipeline_calls!=1 || V.pipeline_result){result=FV_PIPELINE_FAILED;goto applied;}
    if(V.spi_calls!=1 || V.spi_result || V.spi_bytes!=256){result=FV_SENSOR_FAILED;goto applied;}
    U roi0=V.roi0;
    if(target==7)roi0=(roi0&0xffff0000u)|((roi0&65535)-158);
    if(VIDEO_CFG[1]!=target || VIDEO_CFG[2]!=8 || *(const u16 *)(VIDEO_CFG+10)!=(target==7?160:476) ||
       R32(0x6cc59c)!=roi0 || R32(0x6cc5a0)!=V.roi1){result=FV_CONFIG;goto applied;}
    V.ready_rate=R32(0x6c172c);V.ready_tick=NOW;
    ((void (*)(void))0x1f0a1c)();
    if(target==5)V.dirty=0;
    V.switches++;result=FV_OK;
applied:
    V.applying=0;
    if(result && target==5)V.need_recovery=1;
done:
    V.result=result;barrier();V.ack=seq;
}
ARM U fast_video_wait(U queue,void *message,U timeout,U flags){
    if(queue!=R32(0x6c14e8) || message!=(void *)0x6c14ec || flags || V.enabled!=2)
        return ((U (*)(U,void *,U,U))0x186b70)(queue,message,timeout,flags);
    for(;;){
        U result=((U (*)(U,void *,U,U))0x186b70)(queue,message,2,flags);
        /* 原消息优先交还原视频任务处理，不产生伪造消息。 */
        if(result)return result;
        fast_video_service();
        if(V.enabled!=2)return 0;
    }
}
