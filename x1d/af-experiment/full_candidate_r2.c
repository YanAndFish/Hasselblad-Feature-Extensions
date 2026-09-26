/* X1D 1.25.0 FARM apps 827fa74。全程自有单次AF判定，临时RAM实验。 */
typedef unsigned int u32;
typedef signed int s32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
#define R32(a) (*(volatile u32 *)(a))
#define R16(a) (*(volatile u16 *)(a))
#define RS16(a) (*(volatile s16 *)(a))
#define R8(a) (*(volatile u8 *)(a))
#define NOW R32(0x6badd0)
#define CAMERA_STATE R8(0x6bb46c)
#define COUNT R16(0x6bc954)
#define CMD RS16(0x6bb5a0)
#define PREV_CMD RS16(0x6bb5a2)
#define CV(i) R32(0x6bb5cc+4*(i))
#define POS(i) RS16(0x6bbd9c+2*(i))
#define SPEED 20000
#define FINE_SPEED 8000
#define CAPACITY 64
enum { OFF, WAIT_START, PROBE, ASCEND, MOVE_START, FINE_SCAN, MOVE_PEAK, VERIFY, DONE, FAILED };
enum { OK, CONFIG, NO_DATA, TIME_LIMIT, TRAVEL_LIMIT, WRONG_DIRECTION, BAD_CV,
       BAD_COUNT, ENDPOINT, LENS_ERROR, POSITION_ERROR, WEAK_PEAK, CANCELLED, BAD_STATE };
struct Trace { u32 tick, phase; s32 command, position; u32 cv; };
struct FullState {
    u32 magic,abi,armed,boundary_hint,generation,phase,reason,calls,reversals,confirmations;
    u32 owned,started,leg_started,seen,waiting_reset,skip,samples,up,down;
    s32 direction,command,origin,last_position,best_index;
    u32 best_cv,noise,roi0,roi1,rate,configured,pending_error;
    s32 fine_start,fine_end,coarse_peak,target,command_target;
    u32 move_started,reply_seen,reply_status,reply_tick,corrections,position_tolerance;
    s32 physical;
    u32 position_tick,position_seq,raw_cv,raw_tick,raw_seq,verify_seq,verify_points;
    u32 stopped_tick,position_baseline,blocked_commands,send_returns,trace_count,trace_overflow;
    s32 positions[CAPACITY];
    u32 cvs[CAPACITY];
    struct Trace trace[12];
    u32 canary;
};
__attribute__((section(".data.state"),used))
volatile struct FullState af_state={.magic=0x41464f57,.abi=3,.canary=0x574f4641};
#define S af_state
static u32 mag(s32 v){return v<0?(u32)-v:(u32)v;}
static u32 max(u32 a,u32 b){return a>b?a:b;}
static u32 median3(u32 a,u32 b,u32 c){if(a>b){u32 t=a;a=b;b=t;}if(b>c){u32 t=b;b=c;c=t;}return a>b?a:b;}
static s32 sign(s32 v){return (v>0)-(v<0);}
static int enabled(void){return S.armed!=0;}
static int profile(void){return R8(0x2adc79)==18 && !R8(0x2adc8c) &&
    R32(0x2adc2c)==SPEED && R32(0x2adc30)==SPEED && R32(0x6bc9b0)==SPEED;}
static void error(u32 why){if(!S.pending_error)S.pending_error=why;}
static int position_valid(s32 p){return p>=-32760 && p<=32760 && mag(p-S.origin)<=8192;}

/* 从已核对原函数首字之后进入，复用协议和驱动，不进入其搜索判定。 */
__attribute__((naked,noinline,target("arm"))) static void real_speed(s32 v){
    __asm__ volatile("push {fp,lr}\nldr pc,1f\n1:.word 0x1a0244");
}
__attribute__((naked,noinline,target("arm"))) static void real_position(s32 p){
    __asm__ volatile("push {fp,lr}\nldr pc,1f\n1:.word 0x1a037c");
}
static void trace(s32 command){
    u32 i=S.trace_count;
    if(i<12){S.trace[i].tick=NOW;S.trace[i].phase=S.phase;S.trace[i].command=command;
        S.trace[i].position=S.physical;S.trace[i].cv=S.raw_cv;S.trace_count=i+1;}
    else S.trace_overflow++;
}
static void drive(s32 command){
    S.command=command;trace(command);real_speed(command);S.send_returns++;
}
static void clear_scan(u32 phase,s32 direction,s32 speed){
    s32 old=CMD;
    S.phase=phase;S.direction=direction;S.leg_started=NOW;
    S.samples=0;S.up=0;S.down=0;S.best_cv=0;S.best_index=-1;S.noise=1;
    S.waiting_reset=((old>0)!=(direction>0));S.seen=S.waiting_reset?0:COUNT;S.skip=1;
    drive(direction*speed);
}
static void finish(u32 why){
    if(S.phase==DONE || S.phase==FAILED)return;
    if(why && !S.reason)S.reason=why;
    S.phase=why?FAILED:DONE;drive(0);
    if(!why){R16(0x6bb5a8)=(u16)S.coarse_peak;R16(0x6bb5ac)=(u16)S.command_target;S.confirmations++;}
    /* 仅复用正常AF的停止同步、结果消息和关闭镜头CDAF流程。 */
    ((void (*)(u32,u32))0x19dd70)(why?1:0,0);
    ((void (*)(void))0x199ccc)();CAMERA_STATE=7;
}
void af_reset_owned(u32 caller){
    if(caller!=0x19bbf0){if(S.owned && S.phase<DONE)error(BAD_STATE);return;}
    if(!enabled()){S.owned=0;S.phase=OFF;return;}
    u32 generation=S.generation+1;
    volatile u32 *p=(volatile u32 *)&S;
    for(u32 i=4;i<sizeof(S)/4-1;i++)p[i]=0;
    S.generation=generation;S.owned=1;S.phase=WAIT_START;S.best_index=-1;S.started=NOW;
    if(S.armed!=2 || !profile())error(CONFIG);
}
/* 非本算法的运动命令不进入驱动；正常取消的零速度始终允许。 */
s32 af_speed_gate(s32 command,u32 caller){
    if(!S.owned)return command;
    if(caller==0x1a1f68 && S.phase==WAIT_START){
        S.origin=S.physical;S.started=NOW;S.leg_started=NOW;S.phase=PROBE;
        S.direction=R8(0x2adc78)==1?-1:1;S.command=S.direction*SPEED;
        /* 只保留已收到的端点事实，不保留上一轮错误。离开端点后不用此提示。 */
        if((S.boundary_hint&3) && mag(S.physical-(s16)(S.boundary_hint>>16))<=64)
            S.direction=(S.boundary_hint&3)==1?-1:1;
        S.command=S.direction*SPEED;
        S.waiting_reset=((PREV_CMD>0)!=(S.command>0));S.seen=S.waiting_reset?0:COUNT;S.skip=1;
        if(!S.position_seq || !profile() || S.pending_error){error(CONFIG);S.command=0;}
        trace(S.command);return S.command;
    }
    if(!command)return 0;
    S.blocked_commands++;return 65536;
}
int af_position_gate(void){if(!S.owned)return 0;S.blocked_commands++;return 1;}
void af_observe_position(const u8 *message){
    if(!S.owned || S.phase>=DONE)return;
    S.physical=(s16)((u32)message[5]|((u32)message[6]<<8));S.position_tick=NOW;S.position_seq++;
}
void af_observe_cv(const u8 *message){
    if(!S.owned || S.phase>=DONE)return;
    S.raw_cv=(u32)message[4]|((u32)message[5]<<8)|((u32)message[6]<<16)|((u32)message[7]<<24);
    S.raw_tick=NOW;S.raw_seq++;
}
int af_position_reply(const u8 *message){
    if(!S.owned)return 0;
    if(S.phase==MOVE_START || S.phase==MOVE_PEAK){
        S.reply_status=message[4];S.reply_tick=NOW;S.reply_seen=1;
        if(message[4]!=0)error(LENS_ERROR);
    }
    return 1;
}
int af_boundary(s32 direction){
    if(!S.owned)return 0;
    if(S.phase==WAIT_START || S.phase>=DONE)return 1;
    /* 端点回包可能在折返后重复；仅采纳当前仍朝该端点的运动。 */
    if((S.phase==PROBE || S.phase==ASCEND || S.phase==FINE_SCAN) && S.direction!=direction)return 1;
    S.boundary_hint=((u32)(u16)S.physical<<16)|(direction>0?1u:2u);
    error(ENDPOINT);drive(0);return 1;
}
__attribute__((target("arm"))) u32 af_wait(u32 a,u32 b,u32 *events,u32 timeout){
    int active=S.owned && CAMERA_STATE>=3 && CAMERA_STATE<=6;
    u32 result=((u32 (*)(u32,u32,u32 *,u32))0x189e4c)(a,b,events,active?20:timeout);
    if(active && !result){*events=0;return 1;}return result;
}
static void move_to(s32 target,u32 phase){
    if(!position_valid(target)){error(TRAVEL_LIMIT);return;}
    drive(0);S.phase=phase;S.target=target;S.command_target=target;
    S.move_started=NOW;S.reply_seen=0;S.corrections=0;S.position_baseline=S.position_seq;
    trace(target);real_position(target);S.send_returns++;
}
/* 仅用于已成括号的局部峰值；整数缩放和有界除法避免浮点库/溢出。 */
static s32 divide(s32 numerator,s32 denominator){
    u32 a=mag(numerator),b=mag(denominator),q=0,r=0;
    for(u32 i=32;i;i--){r=(r<<1)|((a>>(i-1))&1);if(r>=b){r-=b;q|=1u<<(i-1);}}
    return ((numerator<0)!=(denominator<0))?-(s32)q:(s32)q;
}
static int bracket(s32 *low,s32 *high){
    if(S.best_index<=0 || (u32)S.best_index+1>=S.samples)return 0;
    if(S.phase==FINE_SCAN){
        u32 i=(u32)S.best_index;
        if(i<2 || i+2>=S.samples || S.cvs[i-2]>=S.cvs[i-1] || S.cvs[i-1]>=S.cvs[i] ||
           S.cvs[i+2]>=S.cvs[i+1] || S.cvs[i+1]>=S.cvs[i])return 0;
    }
    s32 best=S.positions[S.best_index],a=best,b=best;u32 found=0;
    for(u32 i=0;i<S.samples;i++){
        if(S.best_cv-S.cvs[i]<max(S.noise*6,S.best_cv/(S.phase==FINE_SCAN?100:20)))continue;
        s32 p=S.positions[i];
        if(p<best && (!(found&1)||p>a)){a=p;found|=1;}
        if(p>best && (!(found&2)||p<b)){b=p;found|=2;}
    }
    *low=a;*high=b;return found==3;
}
static s32 peak_position(void){
    s32 i=S.best_index,p=S.positions[i],left=S.positions[i-1]-p,right=S.positions[i+1]-p;
    s32 a=(s32)S.cvs[i-1]-(s32)S.best_cv,b=(s32)S.cvs[i+1]-(s32)S.best_cv;
    if(!left || !right || sign(left)==sign(right) || mag(left)>512 || mag(right)>512 || a>=0 || b>=0)return p;
    while(mag(a)>511 || mag(b)>511){a/=2;b/=2;}
    s32 denominator=2*(a*right-b*left);
    if(!denominator)return p;
    s32 delta=divide(a*right*right-b*left*left,denominator);
    if(mag(delta)>max(mag(left),mag(right)))return p;
    s32 answer=p+delta;
    if(answer<=p+(left<right?left:right) || answer>=p+(left>right?left:right))return p;
    return answer;
}
static u32 scan_noise(u32 n){
    /* 全段二阶差分的中位数：孤立噪声和窄峰局部曲率均不独占估计。
       数组受CAPACITY约束，最多62项；不在首个偶然上坡后冻结噪声。 */
    u32 values[CAPACITY],count=0;
    for(u32 i=2;i<=n;i++){
        s32 d=(s32)S.cvs[i]-2*(s32)S.cvs[i-1]+(s32)S.cvs[i-2];
        u32 v=mag(d),j=count++;
        while(j && values[j-1]>v){values[j]=values[j-1];j--;}
        values[j]=v;
    }
    return max(1,values[count/2]/2);
}
static void accept(s32 position,u32 cv){
    u32 n=S.samples;
    if(!cv || cv>0x1fffffff){error(BAD_CV);return;}
    if(!position_valid(position)){error(TRAVEL_LIMIT);return;}
    if(n){s32 travel=(position-S.last_position)*S.direction;
        if(travel<0){error(WRONG_DIRECTION);return;}if(!travel)return;}
    if(n>=CAPACITY){error(BAD_COUNT);return;}
    S.positions[n]=position;S.cvs[n]=cv;S.samples=n+1;S.last_position=position;
    if(cv>S.best_cv){S.best_cv=cv;S.best_index=(s32)n;}
    if(n<4)return;
    s32 d0=(s32)S.cvs[n-3]-(s32)S.cvs[n-4],d1=(s32)S.cvs[n-2]-(s32)S.cvs[n-3];
    s32 d2=(s32)S.cvs[n-1]-(s32)S.cvs[n-2],d3=(s32)cv-(s32)S.cvs[n-1];
    /* 用局部变化估计噪声；不要求宽缓边缘先损失固定百分比的反差。 */
    u32 local_noise=max(1,median3(mag(d1-d0),mag(d2-d1),mag(d3-d2))/2);
    S.noise=S.phase==FINE_SCAN?scan_noise(n):local_noise;
    if(S.noise>0x3ffffff)S.noise=0x3ffffff;
    s32 noise=(s32)S.noise;
    S.up=d1>=0 && d2>=0 && d3>=0 && ((d1>0)+(d2>0)+(d3>0)>=2) && (s32)cv-(s32)S.cvs[n-4]>=noise*4;
    S.down=(d1<=0 && d2<=0 && d3<=0 && ((d1<0)+(d2<0)+(d3<0)>=2)) ||
        S.best_cv-max(cv,max(S.cvs[n-1],S.cvs[n-2]))>S.best_cv/4;
    if(S.phase==PROBE && S.up)S.phase=ASCEND;
    int decline=S.down && S.best_cv-cv>=S.noise*6;
    if(!decline)return;
    if(S.phase==PROBE && S.best_index==0){
        if(S.reversals){error(WEAK_PEAK);return;}
        S.reversals++;clear_scan(ASCEND,-S.direction,SPEED);return;
    }
    s32 lo,hi;
    if(!bracket(&lo,&hi))return;
    if(S.phase==PROBE || S.phase==ASCEND){
        s32 p=S.positions[S.best_index];u32 margin=max(64,max(mag(p-lo),mag(hi-p))*3);
        if(margin>960)margin=960;
        S.coarse_peak=p;S.fine_start=p-(s32)margin*S.direction;S.fine_end=p+(s32)margin*S.direction;
        move_to(S.fine_start,MOVE_START);
    } else if(S.phase==FINE_SCAN){
        s32 p=peak_position();
        /* 镜头加性校准是已知模型输入；不复用原厂方向搜索或自适应重试算法。 */
        s32 offset=((s32 (*)(void))0x1a502c)();
        if(mag(offset)>127){error(CONFIG);return;}
        S.coarse_peak=p;
        move_to(p+offset,MOVE_PEAK);
    }
}
int af_event(u32 *events){
    if(!S.owned)return 0;
    u32 state=CAMERA_STATE,t=NOW,mask=*events;S.calls++;
    if(state==0 || state==7){
        if(S.phase<DONE){if(!S.reason)S.reason=CANCELLED;S.phase=FAILED;}
        S.owned=0;return 0;
    }
    if(state<3)return 0;
    *events=0;
    u32 boundary=S.pending_error==ENDPOINT;
    if(boundary)S.pending_error=0;
    if(state!=3)error(BAD_STATE);
    if(mask&~0x10u)error(LENS_ERROR);
    if(S.armed!=2 || !profile())error(CONFIG);
    if(S.phase==DONE || S.phase==FAILED)return 1;
    if(S.pending_error){finish(S.pending_error);return 1;}
    if(S.phase==WAIT_START){if(t-S.started>=500)finish(NO_DATA);return 1;}
    if(t-S.started>=2400)error(TIME_LIMIT);
    if(!S.position_seq || t-S.position_tick>=100)error(NO_DATA);
    if(!position_valid(S.physical))error(TRAVEL_LIMIT);
    if(S.configured && (S.roi0!=R32(0x6cc59c)||S.roi1!=R32(0x6cc5a0)||S.rate!=R32(0x6bcb44)))error(CONFIG);
    if(S.pending_error){finish(S.pending_error);return 1;}
    if(boundary){
        if((S.phase==PROBE || S.phase==ASCEND) && !S.reversals){
            S.reversals++;clear_scan(ASCEND,-S.direction,SPEED);
        }else finish(ENDPOINT);
        return 1;
    }
    if(S.phase==MOVE_START || S.phase==MOVE_PEAK){
        if(t-S.move_started>=600){finish(TIME_LIMIT);return 1;}
        if(!S.reply_seen || S.position_seq==S.position_baseline || t-S.reply_tick<30)return 1;
        s32 tolerance=((s32 (*)(void))0x1a5318)();
        if(tolerance<1 || tolerance>127){finish(CONFIG);return 1;}
        if(S.phase==MOVE_PEAK && S.best_index>0){
            u32 half_step=max(2,mag(S.positions[S.best_index]-S.positions[S.best_index-1])/2);
            if((u32)tolerance>half_step)tolerance=(s32)half_step;
        }
        S.position_tolerance=(u32)tolerance;
        s32 difference=S.target-S.physical;
        if(mag(difference)>(u32)tolerance){
            if(S.corrections || t-S.reply_tick<60){if(S.corrections)finish(POSITION_ERROR);return 1;}
            s32 corrected=S.command_target+difference;
            if(!position_valid(corrected)){finish(TRAVEL_LIMIT);return 1;}
            S.corrections=1;S.command_target=corrected;S.reply_seen=0;S.position_baseline=S.position_seq;
            trace(corrected);real_position(corrected);S.send_returns++;return 1;
        }
        if(S.phase==MOVE_START){clear_scan(FINE_SCAN,S.direction,FINE_SPEED);return 1;}
        S.phase=VERIFY;S.stopped_tick=t;S.verify_seq=S.raw_seq;S.verify_points=0;return 1;
    }
    if(S.phase==VERIFY){
        if(t-S.stopped_tick>=250){finish(WEAK_PEAK);return 1;}
        if(t-S.stopped_tick<50 || S.verify_seq==S.raw_seq)return 1;
        S.verify_seq=S.raw_seq;
        if(t-S.raw_tick>40 || mag(S.physical-S.target)>S.position_tolerance || !S.raw_cv || S.raw_cv>0x1fffffff){S.verify_points=0;return 1;}
        if(S.raw_cv>=S.best_cv-max(S.best_cv/20,S.noise*4))S.verify_points++;else S.verify_points=0;
        if(S.verify_points>=3)finish(OK);return 1;
    }
    if(S.phase==PROBE && t-S.leg_started>=120 && S.samples>=5 && !S.reversals){
        S.reversals++;clear_scan(ASCEND,-S.direction,SPEED);return 1;
    }
    if(t-S.leg_started>=(S.phase==PROBE?250:700)){finish(TIME_LIMIT);return 1;}
    if(S.phase==FINE_SCAN && (S.physical-S.fine_end)*S.direction>0){finish(WEAK_PEAK);return 1;}
    if(S.waiting_reset){if((PREV_CMD>0)!=(S.command>0))return 1;S.waiting_reset=0;S.seen=0;}
    u32 n=COUNT;
    if(n>500 || n<S.seen){finish(BAD_COUNT);return 1;}
    for(u32 i=S.seen;i<n;i++){
        S.seen=i+1;if(S.skip){S.skip--;continue;}
        if(!S.configured){S.roi0=R32(0x6cc59c);S.roi1=R32(0x6cc5a0);S.rate=R32(0x6bcb44);S.configured=1;}
        u32 phase=S.phase;s32 command=S.command;accept(POS(i),CV(i));
        if(S.pending_error){finish(S.pending_error);break;}
        if(S.command!=command || (S.phase!=phase && !(phase==PROBE && S.phase==ASCEND)))break;
    }
    return 1;
}

#define ENTRY __attribute__((naked,used,target("arm"),section(".text.entry")))
ENTRY void dispatch_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nsub r0,fp,#0x94\nbl af_event\ncmp r0,#0\npop {r0-r3,r12,lr}\n"
    "ldrne pc,1f\nmovw r3,#0xb46c\nldr pc,2f\n1:.word 0x19d198\n2:.word 0x19bb98");}
ENTRY void reset_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmov r0,lr\nbl af_reset_owned\npop {r0-r3,r12,lr}\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a4954");}
ENTRY void speed_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmov r1,lr\nbl af_speed_gate\nstr r0,[sp]\ncmp r0,#65536\npop {r0-r3,r12,lr}\n"
    "bxeq lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a0244");}
ENTRY void position_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_position_gate\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a037c");}
ENTRY void position_observer_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_observe_position\npop {r0-r3,r12,lr}\npush {r4,fp,lr}\nldr pc,1f\n1:.word 0x1a1cdc");}
ENTRY void cv_observer_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_observe_cv\npop {r0-r3,r12,lr}\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a1a9c");}
ENTRY void position_reply_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_position_reply\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {r4,r5,fp,lr}\nldr pc,1f\n1:.word 0x1a0ec0");}
ENTRY void near_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmov r0,#1\nbl af_boundary\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a049c");}
ENTRY void far_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmvn r0,#0\nbl af_boundary\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a06e8");}
