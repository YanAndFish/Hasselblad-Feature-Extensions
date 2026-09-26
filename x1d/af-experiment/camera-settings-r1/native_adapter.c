/* 固定 X1D 1.25.0 的离线集成适配器。采样关联入口尚未接入实机。 */
#include "native_config.h"
#include "rolling_direction.h"
#define R8(a) (*(volatile unsigned char *)(a))
#define R16(a) (*(volatile unsigned short *)(a))
#define RS16(a) (*(volatile signed short *)(a))
#define R32(a) (*(volatile u32 *)(a))
#define CMD RS16(0x6bb5a0)
#define COUNT R16(0x6bc954)
struct NaAdapter {
    u32 generation,count,allow_actuation,previous_valid,last_slow_count,previous_count,config_status;
    u32 previous_kind,command_sequence;
    s32 last_command;
    float previous_peak;
    struct NaTiming timing;
    struct NaSample samples[5];
    struct NaResult result;
};
__attribute__((section(".data.state"),used)) struct NaAdapter na_adapter={0};
/* 候选初值启用阶段覆盖；每次发命令仍核对固定镜头标识与本轮配置。 */
__attribute__((section(".data.state"),used)) u32 na_speed_overrides=1;
#define A na_adapter
__attribute__((section(".text.na_api"))) void na_begin(u32 generation){
    A=(struct NaAdapter){.generation=generation};A.config_status=na_config_latch(generation);
}
__attribute__((section(".text.na_api"))) void na_cycle_reset(void){
    ((void (*)(void))0x1a4950)();na_begin(A.generation+1);
}
/* 返回本次原厂封包使用的 signed16 参数，不能在返回后重读跨任务共享 CMD。 */
__attribute__((section(".text.na_api"))) s32 na_stage_speed(u32 stage,s32 original){
    s32 chosen=na_speed_overrides==1 && !A.config_status && R8(0x2adc79)==18?na_config_command(stage,original):original;
    /* 仅初始试探调用点使用无证据搜索偏好；后续判向、端点反转与精扫保持原厂符号。
       固定 FARM 两个端点处理器支持 negative=inf，positive=near。 */
    if(stage==NA_PROBE && !A.config_status && R8(0x2adc79)==18 &&
       (na_config_bank.active.flags&NA_FAR_FIRST) && chosen>0)chosen=-chosen;
    A.command_sequence++;A.last_command=chosen;
    A.timing.command_in_flight=1;A.timing.commanded_velocity_bound=0;
    ((void (*)(s32))0x1a0240)(chosen);
    return (signed short)chosen;
}
__attribute__((section(".text.na_api"))) void na_probe_speed(s32 v){na_stage_speed(NA_PROBE,v);}
__attribute__((section(".text.na_api"))) void na_fast_speed(s32 v){na_stage_speed(NA_FAST,v);}
__attribute__((section(".text.na_api"))) void na_fine_speed(s32 v){na_stage_speed(NA_FINE,v);}
/* 仅由离线用例供应已关联数据。未来采集入口必须证明帧、位置、时刻对应关系。 */
__attribute__((section(".text.na_api"))) void na_supply(const struct NaSample *s){
    if(s->generation!=A.generation){A.count=0;A.previous_valid=0;return;}
    if(A.count && s->native_count<=A.samples[A.count-1].native_count){A.count=0;A.previous_valid=0;}
    if(A.count==5){for(u32 i=0;i<4;i++)A.samples[i]=A.samples[i+1];A.count=4;}
    A.samples[A.count++]=*s;
}
static int assess(void){
    u32 n=COUNT;
    A.result=(struct NaResult){.reason=NA_METADATA,.safe_speed_ratio=1};
    if(A.count<2 || n<A.count || n>500 || A.samples[A.count-1].native_count!=n)return 0;
    /* 每项与当前原厂已接受数组比对；旧周期、反向后残留或错配不能接管。 */
    for(u32 i=0;i<A.count;i++){
        u32 j=n-A.count+i;
        if(A.samples[i].position!=RS16(0x6bbd9c+j*2) || A.samples[i].cv!=R32(0x6bb5cc+j*4))return 0;
    }
    struct NaTiming timing=A.timing;timing.now=R32(0x6badd0);
    if(timing.command_sequence!=A.command_sequence){timing.command_in_flight=1;timing.commanded_velocity_bound=0;}
    na_assess(A.samples,A.count,&timing,&A.result);
    return 1;
}
/* 原厂函数仍计算 maxCV；其后阈值、低反差检查、方向事件与状态迁移均继续执行。 */
float na_direction(unsigned int *maximum){
    float original=((float (*)(unsigned int *))0x19e47c)(maximum);
    if(A.config_status || R8(0x2adc79)!=18 || !(na_config_bank.active.flags&NA_NEW_DIRECTION))return original;
    if(R8(0x6bb46c)!=3)return original;
    u32 count=COUNT,generation=A.generation,minimum=R32(0x6bb5bc);
    if(count<3 || count>500 || !minimum)return 0;
    u32 n=count<5?count:5,cv[5],maximum_cv=0;s32 pos[5];
    for(u32 i=0;i<n;i++){
        u32 j=count-n+i;pos[i]=RS16(0x6bbd9c+2*j);cv[i]=R32(0x6bb5cc+4*j);
        if(i>=n-3 && cv[i]>maximum_cv)maximum_cv=cv[i];
    }
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    /* 发布 count 后才是完整 pair；复核快照及周期，拒绝重置/覆盖期间的数据。
       此检查只保证读取一致性，不把 FIFO 配对升级为同一曝光时刻。 */
    if(COUNT!=count || A.generation!=generation || R32(0x6bb5bc)!=minimum || R8(0x6bb46c)!=3)return 0;
    for(u32 i=0;i<n;i++){
        u32 j=count-n+i;if(pos[i]!=RS16(0x6bbd9c+2*j) || cv[i]!=R32(0x6bb5cc+4*j))return 0;
    }
    if(COUNT!=count || A.generation!=generation)return 0;
    float result=as_direction(pos,cv,n,minimum);*maximum=maximum_cv;
    return result;
}
void na_before_peak(void){
    if(R8(0x6bb46c)!=4 || !assess() || !A.result.prediction_valid){A.previous_valid=0;return;}
    if(A.previous_valid && A.previous_count==COUNT)return;
    float peak=A.result.peak_position,difference=peak-A.previous_peak;
    if(difference<0)difference=-difference;
    u32 stable=A.previous_valid && A.previous_kind==A.result.prediction_kind &&
               (A.result.prediction_kind==1 || difference<=A.result.position_step);
    A.previous_valid=1;A.previous_peak=peak;A.previous_count=COUNT;A.previous_kind=A.result.prediction_kind;
    if(!stable || A.allow_actuation!=1 || A.config_status || A.last_slow_count==COUNT || A.result.safe_speed_ratio>=1)return;
    s32 command=CMD;
    if(!command || (float)command*A.result.velocity_per_tick<=0)return;
    s32 magnitude=command<0?-command:command;
    /* 读取原厂当前精扫速度，不写固定速度或镜头参数。 */
    s32 floor=((s32 (*)(u32))0x1a3e08)(R8(0x6bcb7c));
    if(na_speed_overrides==1)floor=na_config_command(NA_FINE,floor);
    if(floor<=0 || floor>32767 || magnitude<=floor)return;
    float ratio=A.result.safe_speed_ratio;
    s32 limited=(s32)((float)magnitude*ratio);if(limited<floor)limited=floor;
    if(limited>=magnitude)return;
    A.last_slow_count=COUNT;
    A.command_sequence++;A.last_command=command<0?-limited:limited;
    A.timing.command_in_flight=1;A.timing.commanded_velocity_bound=0;
    ((void (*)(s32))0x1a0240)(command<0?-limited:limited);
}
extern void as_native_near(void);
void as_near_limit(void){
    /* 仅远端优先、仍无判向结论的搜索：远端已到达后，在另一端按原厂失败事件退出。
       原厂 near/far 处理器检查 +3，而 far 只设置 +2；不让此非对称性增加第三段扫全程。 */
    if(!A.config_status && R8(0x2adc79)==18 && (na_config_bank.active.flags&NA_FAR_FIRST) &&
       R8(0x6bb46c)==3 && R8(0x6bb59e)==1 && CMD>0){((void (*)(u32))0x1a4890)(0x2000);return;}
    as_native_near();
}
/* 回放被覆盖的原厂 prologue，并继续执行全部越峰检测。 */
__attribute__((naked,noinline,target("arm"),section(".text.na_api"))) void na_peak_entry(void){
    __asm__ volatile("push {r0-r3,r12,lr}\nbl na_before_peak\npop {r0-r3,r12,lr}\n"
                     "push {fp,lr}\nldr pc,1f\n1:.word 0x19d5cc");
}
