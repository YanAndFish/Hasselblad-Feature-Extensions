#include "af_policy.h"
#include "start_phase.h"
#define R8(a) (*(volatile unsigned char *)(a))
#define R32(a) (*(volatile u32 *)(a))
#define CMD (*(volatile signed short *)0x6bb5a0)
struct AfCycle {u32 generation,status;struct AfPolicy policy;};
__attribute__((section(".data.state"),used)) struct AfCycle af_cycle={0};
__attribute__((section(".data.state"),used)) struct NaStartPhase na_start_phase={0};
#define A af_cycle
void na_begin(u32 generation){
    A=(struct AfCycle){.generation=generation};A.status=af_policy_begin(&A.policy,generation);
    na_start_reset(&na_start_phase,generation);
    af_window_reset(generation);
}
void na_cycle_reset(void){((void (*)(void))0x1a4950)();na_begin(A.generation+1);}
static int valid(void){return !A.status && A.policy.eligible && af_policy_current(&A.policy);}
static int rules_valid(void){
#ifdef AF_PROFILE_TEST
    return valid();
#else
    return A.generation!=0;
#endif
}
static int far_first_enabled(void){
#ifdef AF_PROFILE_TEST
    return rules_valid() && A.policy.far_first;
#else
    /* 发布版是固定规则，不从配置字段读取方向开关。 */
    return rules_valid();
#endif
}
u32 af_current_advance(void){
#ifdef AF_PROFILE_TEST
    return valid()?A.policy.fine_advance_ms:0;
#else
    /* 发布规则独立于速度白名单；每轮初始化后对所有镜头生效。 */
    return rules_valid()?100:0;
#endif
}
/* Read only parameters already accepted by the factory NEW LENS path. No getter call can initiate a query. */
u32 af_reported_start_speed(void){
    if(R8(0x2adc79)!=18)return 0;
    u32 row=0x2ad998+18*36;
    u32 offset=R8(0x6bcb7d),lo=(R8(0x6bcb7e)-offset)&255,hi=(R8(0x6bcb7f)-offset)&255;
    if(!lo || !hi || lo==255 || hi==255 || R8(row+5)!=lo || R8(row+6)!=hi)return 0;
    u32 speed=R32(row+(R8(0x6bcb7c)?16:12));
    if(R8(0x2adc79)!=18 || R8(row+5)!=lo || R8(row+6)!=hi || !speed || speed>32767)return 0;
    return speed;
}
static s32 choose(u32 stage,s32 original){
    if(!original || original<-32767 || original>32767 || stage>AP_FINE || !valid())return original;
    u32 value=stage==AP_PROBE?A.policy.probe:(stage==AP_FAST?A.policy.fast:A.policy.fine);
    if(!value || value>32767)return original;
    return original<0?-(s32)value:(s32)value;
}
static s32 emit(s32 value){((void (*)(s32))0x1a0240)(value);return (signed short)value;}
s32 na_stage_speed(u32 stage,s32 original){
    int enabled=valid();s32 chosen=enabled?choose(stage,original):original;
    if(stage==AP_PROBE && rules_valid() && A.policy.start_speed && original && original>=-32767 && original<=32767){
        u32 low=enabled?A.policy.start_speed:0;
        if(low==AP_DYNAMIC_70){u32 reported=A.policy.reported_speed;low=reported?reported*7/10:0;}
        if((low && low<=32767) || !enabled){
            (void)na_start_arm(&na_start_phase,A.generation,original);
            if(na_start_active(&na_start_phase,A.generation))chosen=low?(original<0?-(s32)low:(s32)low):original;
        }
    }
    if(stage==AP_FAST || stage==AP_FINE)na_start_cancel(&na_start_phase);
    if(stage==AP_PROBE && far_first_enabled() && chosen>0)chosen=-chosen;
    return emit(chosen);
}
s32 na_resume_probe(s32 original){return emit(choose(AP_PROBE,original));}
void na_start_accepted(u32 count){if(count && count<=500){na_start_sample(&na_start_phase);af_window_sample(count);}}
extern void nc_probe_resume(s32);
void na_after_direction(void){
    if(!rules_valid() || R8(0x6bb46c)!=3)return;
    u32 generation=A.generation,original=na_start_take(&na_start_phase,generation,A.policy.start_samples);
    if(!original || A.generation!=generation || !rules_valid() || R8(0x6bb46c)!=3)return;
    s32 current=CMD;if(current)nc_probe_resume(current<0?-(s32)original:(s32)original);
}
void na_probe_speed(s32 v){na_stage_speed(AP_PROBE,v);}
void na_fast_speed(s32 v){na_stage_speed(AP_FAST,v);}
void na_fine_speed(s32 v){na_stage_speed(AP_FINE,v);}
extern void as_native_near(void);
void as_near_limit(void){
    if(far_first_enabled() && R8(0x6bb46c)==3 && R8(0x6bb59e)==1 && CMD>0){
        ((void (*)(u32))0x1a4890)(0x2000);return;
    }
    as_native_near();
}
