/* X1D 1.25.0 FARM apps 827fa74。全程自有单次AF判定，临时RAM实验。 */
#include "fast_video_r5.h"
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
#define CAPACITY 32
enum { OFF, WAIT_START, PROBE, ASCEND, MOVE_START, FINE_SCAN, MOVE_PEAK, VERIFY, DONE, FAILED };
enum { OK, CONFIG, NO_DATA, TIME_LIMIT, TRAVEL_LIMIT, WRONG_DIRECTION, BAD_CV,
       BAD_COUNT, ENDPOINT, LENS_ERROR, POSITION_ERROR, WEAK_PEAK, CANCELLED, BAD_STATE, VIDEO_ERROR };
struct Trace { u32 tick, phase; s32 command, position; u32 cv; };
struct Frame { volatile u32 seq,tick,generation,cv; volatile s32 position; volatile u32 accepted_seq; };
struct FullState {
    volatile u32 magic,abi,armed,boundary_hint,generation,phase,reason,calls,reversals,confirmations;
    volatile u32 owned,started,leg_started,seen,waiting_reset,skip,samples,up,down;
    volatile s32 direction,command,origin,last_position,best_index;
    volatile u32 best_cv,noise,roi0,roi1,rate,configured,pending_error;
    volatile s32 fine_start,fine_end,coarse_peak,target,command_target;
    volatile u32 move_started,reply_seen,reply_status,reply_tick,corrections,position_tolerance;
    volatile s32 physical;
    volatile u32 position_tick,position_seq,raw_cv,raw_tick,raw_seq,verify_seq,verify_points;
    volatile u32 stopped_tick,position_baseline,blocked_commands,send_returns,trace_count,trace_overflow;
    s16 positions[CAPACITY];
    u32 cvs[CAPACITY];
    struct Trace trace[8];
    volatile u32 stop_pending,stable_tick,stable_seq,stable_points;
    volatile s32 stable_position;
    volatile u32 predictions,brake_distance;
    volatile u32 probe_active;
    volatile u32 frame_seq,frame_consumed;
    struct Frame frames[8];
    volatile s32 probe_origin;
    volatile u32 refinements;
    volatile u32 cv_profile,video_state,video_started,video_raw,video_fresh,video_preview,last_full_tick,finish_pending;
    volatile s32 video_command;
    volatile u32 video_mipi;
    volatile u32 canary;
};
__attribute__((section(".data.state"),used))
struct FullState af_state={.magic=0x41464f57,.abi=6,.canary=0x574f4641};
__attribute__((section(".data.state"),used))
volatile u32 af_error_events=0,af_error_generation=0;
typedef char owned_entry_offset_must_match[__builtin_offsetof(struct FullState,owned)==40?1:-1];
#define S af_state
#define V fast_video_state
#define API __attribute__((used))
#define EXTRA(n) __attribute__((noinline,section(".text.extra" #n)))
API int af_boundary(s32 direction);
static int probe_seen(s32 target);
static void probe_move_to(s32 target);
static void settle_probe(void);
static void probe_event(u32 t);
static void launch_probe(void);
static int video_plan(u32 target,s32 command);
static int video_step(u32 t);
static void finish(u32 why);
static void observe_stability(u32 t);
static u32 mag(s32 v){return v<0?(u32)-v:(u32)v;}
static void publish_barrier(void){__asm__ volatile("dmb ish" ::: "memory");}
static u32 max(u32 a,u32 b){return a>b?a:b;}
static u32 median3(u32 a,u32 b,u32 c){if(a>b){u32 t=a;a=b;b=t;}if(b>c){u32 t=b;b=c;c=t;}return a>b?a:b;}
static s32 sign(s32 v){return (v>0)-(v<0);}
static int enabled(void){return S.armed!=0;}
static int profile(void){return R8(0x2adc79)==18 && !R8(0x2adc8c) && !R8(0x6bb598) &&
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
    if(i<8){S.trace[i].tick=NOW;S.trace[i].phase=S.phase;S.trace[i].command=command;
        S.trace[i].position=S.physical;S.trace[i].cv=S.raw_cv;S.trace_count=i+1;}
    else S.trace_overflow++;
}
static void drive(s32 command){
    S.command=command;trace(command);real_speed(command);S.send_returns++;
}
static void clear_scan(u32 phase,s32 direction,s32 speed){
    S.phase=phase;S.direction=direction;S.leg_started=NOW;
    S.samples=0;S.up=0;S.down=0;S.best_cv=0;S.best_index=-1;S.noise=1;
    S.waiting_reset=0;S.seen=S.frame_seq;S.skip=1;
    S.cv_profile=phase==FINE_SCAN && V.session==S.generation;
    if(!S.cv_profile || !video_plan(7,direction*speed))drive(direction*speed);
}
static void finish_now(u32 why){
    if(S.phase==DONE || S.phase==FAILED)return;
    if(why && (!S.reason || why==VIDEO_ERROR))S.reason=why;
    S.phase=why?FAILED:DONE;drive(0);
    if(!why){R16(0x6bb5a8)=(u16)S.coarse_peak;R16(0x6bb5ac)=(u16)S.command_target;S.confirmations++;}
    /* 仅复用正常AF的停止同步、结果消息和关闭镜头CDAF流程。 */
    ((void (*)(u32,u32))0x19dd70)(why?1:0,0);
    ((void (*)(void))0x199ccc)();CAMERA_STATE=7;
}
static EXTRA(5) void finish(u32 why){
    if(S.phase>=DONE)return;
    if(why && !S.reason)S.reason=why;
    if(V.session==S.generation && (S.video_state || V.dirty || V.request!=V.ack)){
        if(!S.finish_pending)S.finish_pending=why+1;
        else if(why && S.finish_pending==1)S.finish_pending=why+1;
        if(S.command)drive(0);
        if(!S.video_state)video_plan(5,0);
        return;
    }
    finish_now(why);
}
static EXTRA(5) int video_plan(u32 target,s32 command){
    if(V.session!=S.generation)return 0;
    if(S.video_state)return 1;
    if(!V.dirty && target==5)return 0;
    if(target==7 && V.dirty && V.target==7 && !V.result && V.request==V.ack)return 0;
    S.video_started=NOW;S.video_command=command;S.video_state=1;
    drive(0);
    if(!fast_video_request(target)){
        V.need_recovery=1;V.session=0;S.video_state=0;finish_now(VIDEO_ERROR);
    }
    return 1;
}
/* 视频任务唯一执行切换；AF只提交单一不可改写请求，丢弃切换前及预热统计。 */
static EXTRA(7) int video_step(u32 t){
    if(!S.video_state)return 0;
    observe_stability(t);
    if(V.external_epoch!=V.session_epoch){
        V.need_recovery=1;V.session=0;publish_barrier();
        if(V.applying)return 1;
        S.video_state=0;finish_now(VIDEO_ERROR);return 1;
    }
    if(t-S.video_started>=350){
        V.need_recovery=1;V.session=0;publish_barrier();
        if(V.applying)return 1;
        S.video_state=0;finish_now(VIDEO_ERROR);return 1;
    }
    if(S.video_state==1){
        if(V.request!=V.ack)return 1;
        publish_barrier();
        if(V.result){
            if(V.target==7 && !V.need_recovery){
                S.finish_pending=VIDEO_ERROR+1;S.video_state=0;video_plan(5,0);return 1;
            }
            V.need_recovery=1;V.session=0;S.video_state=0;finish_now(VIDEO_ERROR);return 1;
        }
        S.roi0=R32(0x6cc59c);S.roi1=R32(0x6cc5a0);S.rate=V.ready_rate;R32(0x6bcb44)=S.rate;
        S.seen=S.frame_seq;S.frame_consumed=S.frame_seq;S.video_raw=S.raw_seq;S.video_fresh=0;S.video_state=2;
        if(V.target==5)S.video_mipi=((u32 (*)(void))0x1fd1a4)();
    }
    if(S.video_raw==S.raw_seq || (s32)(S.raw_tick-V.ready_tick)<=0)return 1;
    S.video_raw=S.raw_seq;
    S.video_fresh++;
    if(V.target==5){
        /* 原厂getter读MIPI picture-end低8位。等两次新结束，排除ACK时在途帧。
           这是发送端条件，不是Linux/Qt已显示证明；未增长仍受350 tick超时。 */
        u32 ends=(((u32 (*)(void))0x1fd1a4)()-S.video_mipi)&255;
        if(ends<2 || ends>=128)return 1;
    }else if(S.video_fresh<3)return 1;
    u32 target=V.target;S.video_state=0;
    S.leg_started+=t-S.video_started;S.move_started+=t-S.video_started;
    if(target==5)S.last_full_tick=t;
    if(S.finish_pending){
        if(target!=5){video_plan(5,0);return 1;}
        u32 why=S.finish_pending-1;S.finish_pending=0;finish_now(why);return 1;
    }
    if(S.video_preview && target==5){video_plan(7,S.video_command);return 1;}
    u32 preview=S.video_preview;S.video_preview=0;S.seen=S.frame_seq;S.skip=1;
    if(S.phase==PROBE){S.stopped_tick=t;S.verify_seq=S.raw_seq;S.verify_points=0;}
    if(S.phase==VERIFY){
        /* 预览穿插没有新的定点动作；保留已实际经过的停稳时间，
           仍清除确认样本并只接纳返回160后的新统计，避免周期刷新饿死确认。 */
        if(!preview)S.stopped_tick=t;
        S.verify_seq=S.raw_seq;S.verify_points=0;
    }
    if(S.video_command)drive(S.video_command);
    return 1;
}
API void af_reset_owned(u32 caller){
    if(caller!=0x19bbf0){if(S.owned && S.phase<DONE)error(BAD_STATE);return;}
    if(!enabled()){S.owned=0;S.phase=OFF;return;}
    S.owned=0;
    u32 generation=S.generation+1,frame_seq=S.frame_seq;
    volatile u32 *p=(volatile u32 *)&S;
    for(u32 i=4;i<sizeof(S)/4-1;i++)p[i]=0;
    S.frame_seq=frame_seq;S.frame_consumed=frame_seq;
    af_error_events=0;af_error_generation=generation;
    S.generation=generation;S.owned=1;S.phase=WAIT_START;S.best_index=-1;S.started=NOW;
    if(V.need_recovery || V.dirty || V.request!=V.ack)error(VIDEO_ERROR);
    if(S.armed!=2 || !profile())error(CONFIG);
}
/* 非本算法的运动命令不进入驱动；正常取消的零速度始终允许。 */
API s32 af_speed_gate(s32 command,u32 caller){
    if(!S.owned)return command;
    if(caller==0x1a1f68 && S.phase==WAIT_START){
        S.origin=S.physical;S.probe_origin=S.physical;S.started=NOW;S.leg_started=NOW;S.phase=PROBE;
        S.direction=R8(0x2adc78)==1?-1:1;S.command=0;
        /* 只保留已收到的端点事实，不保留上一轮错误。离开端点后不用此提示。 */
        if((S.boundary_hint&3) && mag(S.physical-(s16)(S.boundary_hint>>16))<=64)
            S.direction=(S.boundary_hint&3)==1?-1:1;
        S.probe_active=1;S.noise=1;settle_probe();
        S.roi0=R32(0x6cc59c);S.roi1=R32(0x6cc5a0);S.rate=R32(0x6bcb44);S.configured=1;
        S.last_full_tick=NOW;fast_video_begin(S.generation,S.roi0,S.roi1,S.rate);
        if(!S.position_seq || !profile() || S.pending_error){error(CONFIG);S.command=0;}
        trace(S.command);return S.command;
    }
    if(!command)return 0;
    S.blocked_commands++;return 65536;
}
API int af_position_gate(void){if(!S.owned)return 0;S.blocked_commands++;return 1;}
API void af_observe_position(const u8 *message){
    if(!S.owned || S.phase>=DONE)return;
    S.physical=(s16)((u32)message[5]|((u32)message[6]<<8));S.position_tick=NOW;S.position_seq++;
}
API EXTRA(2) u32 af_tag_frame(u32 cv){
    if(!S.owned || S.phase>=DONE || !profile() || S.video_state==1)return 0;
    u32 generation=S.generation;
    u32 seq=S.frame_seq+1;if(!(seq&65535))seq++;
    S.frame_seq=seq;
    struct Frame *p=&S.frames[seq&7];
    p->seq=0;p->accepted_seq=0;publish_barrier();
    p->tick=NOW;p->generation=generation;p->cv=cv;publish_barrier();p->seq=seq;
    return seq&65535;
}
API EXTRA(8) int af_observe_cv(const u8 *message){
    if(!S.owned)return 1;
    if(S.phase>=DONE)return 0;
    u32 tag=(u32)message[2]|((u32)message[3]<<8);
    u32 cv=(u32)message[4]|((u32)message[5]<<8)|((u32)message[6]<<16)|((u32)message[7]<<24);
    struct Frame *p=&S.frames[tag&7];u32 seq=p->seq;publish_barrier();
    u32 tick=p->tick,generation=p->generation,value=p->cv;publish_barrier();
    if(!tag || (seq&65535)!=tag || generation!=S.generation || value!=cv || p->seq!=seq ||
       (s32)(seq-S.frame_consumed)<=0 || NOW-tick>=100){
        if(!S.video_state && (S.phase==ASCEND || S.phase==FINE_SCAN))error(NO_DATA);
        return 0;
    }
    if(!S.video_state && (S.phase==ASCEND || S.phase==FINE_SCAN) && S.command){
        p->position=S.physical;publish_barrier();p->accepted_seq=seq;
    }
    publish_barrier();
    S.frame_consumed=seq;S.raw_cv=cv;S.raw_tick=tick;S.raw_seq++;
    if(!V.dirty && !S.video_state)S.last_full_tick=tick;
    /* 自有八项有界队列与数据事件。原厂双FIFO没有共同帧标记，不参与本轮搜索。 */
    ((void (*)(u32))0x1a4890)(16);return 0;
}
API EXTRA(5) int af_position_reply(const u8 *message){
    if(!S.owned)return 0;
    if((S.phase==MOVE_START || S.phase==MOVE_PEAK) && !S.stop_pending && !S.reply_seen){
        u32 status=message[4];
        S.reply_status=status;S.reply_tick=NOW;S.reply_seen=1;
        /* 固定原厂0x1a0ebc：1=Near Limit，2=Far Limit，3=Jammed。
           仅采纳与在途目标方向相符的限位；重复回复不触发第二次处理。 */
        if(status==1 || status==2){
            s32 direction=status==1?1:-1;
            if((S.command_target-S.physical)*direction<0)error(LENS_ERROR);
            else {S.direction=direction;af_boundary(direction);}
        }else if(status)error(LENS_ERROR);
    }
    return 1;
}
API int af_boundary(s32 direction){
    if(!S.owned)return 0;
    if(S.phase==WAIT_START || S.phase>=DONE)return 1;
    /* 端点回包可能在折返后重复；仅采纳当前仍朝该端点的运动。 */
    if((S.phase==PROBE || S.phase==ASCEND || S.phase==FINE_SCAN) && S.direction!=direction)return 1;
    S.boundary_hint=((u32)(u16)S.physical<<16)|(direction>0?1u:2u);
    error(ENDPOINT);drive(0);return 1;
}
API __attribute__((target("arm"))) u32 af_wait(u32 a,u32 b,u32 *events,u32 timeout){
    int active=S.owned && CAMERA_STATE>=3 && CAMERA_STATE<=6;
    u32 result=((u32 (*)(u32,u32,u32 *,u32))0x189e4c)(a,b,events,active?20:timeout);
    if(active && !result){*events=0;return 1;}return result;
}
static void move_to(s32 target,u32 phase){
    if(!position_valid(target)){error(TRAVEL_LIMIT);return;}
    u32 settled=S.command==0 && S.phase==PROBE && S.stable_seq==S.position_seq &&
        S.stable_points>=3 && NOW-S.stable_tick>=30 && mag(S.physical-S.stable_position)<=2;
    drive(0);S.phase=phase;S.target=target;S.command_target=target;
    S.move_started=NOW;S.reply_seen=0;S.corrections=0;S.position_baseline=S.position_seq;
    /* 停止与CF定点严格分开。三个新位置回包、至少30 tick稳定才允许发CF。 */
    S.stop_pending=1;S.stable_tick=NOW;S.stable_seq=S.position_seq;
    S.stable_position=S.physical;S.stable_points=0;
    /* CF依赖镜头停稳/位置回复；同一160曲线内不为每个微移重复启停视频。
       全幅预览由独立期限安排，仅在停止/扫描阶段切换，不打断在途CF。 */
    if(!S.cv_profile && video_plan(5,0))return;
    if(settled){S.stop_pending=0;trace(target);real_position(target);S.send_returns++;}
}
/* 限位回复所关联的位置只作保守微探测边界，不当作镜头全行程标定。
   刚触及限位的局部探测不再向已知外侧发CF；最多尝试四个未测内侧点。 */
static EXTRA(2) int probe_seen(s32 target){
    for(u32 i=0;i<S.samples;i++)if(mag(S.positions[i]-target)<=2)return 1;
    return 0;
}
static EXTRA(5) void probe_move_to(s32 target){
    u32 hint=S.boundary_hint&3;
    s32 limit=(s16)(S.boundary_hint>>16),inward=hint==1?-1:1;
    if(hint && mag(S.probe_origin-limit)<=256 && (target-limit)*inward<0){
        u32 k;
        for(k=1;k<=4;k++){
            target=S.probe_origin+64*(s32)k*inward;
            if(!probe_seen(target) && (target-limit)*inward>=0)break;
        }
        if(k>4){finish(ENDPOINT);return;}
    }
    move_to(target,MOVE_START);
}
/* 仅用于已成括号的局部峰值；整数缩放和有界除法避免浮点库/溢出。 */
static s32 divide(s32 numerator,s32 denominator){
    u32 a=mag(numerator),b=mag(denominator),q=0,r=0;
    for(u32 i=32;i;i--){r=(r<<1)|((a>>(i-1))&1);if(r>=b){r-=b;q|=1u<<(i-1);}}
    return ((numerator<0)!=(denominator<0))?-(s32)q:(s32)q;
}
static EXTRA(4) int bracket(s32 *low,s32 *high){
    s32 index=S.best_index;u32 count=S.samples,best_cv=S.best_cv,noise=S.noise;
    u32 fine=S.phase==FINE_SCAN;
    if(index<=0 || (u32)index+1>=count)return 0;
    if(fine){
        u32 i=(u32)index;
        if(i<2 || i+2>=count || S.cvs[i-2]>=S.cvs[i-1] || S.cvs[i-1]>=best_cv ||
           S.cvs[i+2]>=S.cvs[i+1] || S.cvs[i+1]>=best_cv)return 0;
    }
    u32 threshold=fine?max(noise*6,best_cv/100):max(noise*3,best_cv/20);
    s32 best=S.positions[index],a=best,b=best;u32 found=0;
    for(u32 i=0;i<count;i++){
        if(best_cv-S.cvs[i]<threshold)continue;
        s32 p=S.positions[i];
        if(p<best && (!(found&1)||p>a)){a=p;found|=1;}
        if(p>best && (!(found&2)||p<b)){b=p;found|=2;}
    }
    *low=a;*high=b;return found==3;
}
static EXTRA(3) s32 peak_position(void){
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
static EXTRA(4) int predict_braking(u32 n){
    if(S.phase!=ASCEND || n<2 || !S.up)return 0;
    s32 h0=mag(S.positions[n-1]-S.positions[n-2]),h1=mag(S.positions[n]-S.positions[n-1]);
    s32 d0=(s32)S.cvs[n-1]-(s32)S.cvs[n-2],d1=(s32)S.cvs[n]-(s32)S.cvs[n-1];
    if(!h0 || !h1 || h0>512 || h1>512 || d0<=0 || d1<=0)return 0;
    while(d0>2047 || d1>2047){d0/=2;d1/=2;}
    s32 g0=divide(d0*256,h0),g1=divide(d1*256,h1);
    if(g0<=g1 || g0-g1<g0/8)return 0;
    s32 ahead=divide(g1*(h0+h1),2*(g0-g1));
    /* 预测只决定提前减速，不据此宣告合焦；随后仍须双侧局部峰和停止验证。 */
    u32 budget=max(400,(u32)h1*2);
    if(ahead<0 || (u32)ahead>budget)return 0;
    S.predictions++;S.brake_distance=budget;
    S.fine_end=S.physical+(ahead+384)*S.direction;
    /* 同向减速保留已采到的上升侧，避免临近峰值重置后丢掉左侧括号。 */
    S.phase=FINE_SCAN;S.leg_started=NOW;S.skip=1;
    S.seen=S.frame_seq;
    drive(S.direction*FINE_SPEED);return 1;
}
static EXTRA(2) void settle_probe(void){
    S.phase=PROBE;S.stopped_tick=NOW;S.verify_seq=S.raw_seq;S.verify_points=0;
    S.stable_tick=NOW;S.stable_seq=S.position_seq;S.stable_position=S.physical;S.stable_points=0;
    if(S.cv_profile && !S.video_state && !V.dirty)video_plan(7,0);
}
static EXTRA(5) void observe_stability(u32 t){
    if(S.stable_seq==S.position_seq)return;
    S.stable_seq=S.position_seq;
    if(mag(S.physical-S.stable_position)>2){
        S.stable_position=S.physical;S.stable_tick=t;S.stable_points=0;S.verify_points=0;
    }else S.stable_points++;
}
static EXTRA(2) void launch_probe(void){
    u32 n=S.samples;
    s32 direction=S.best_index==0?-1:1;
    if(direction<0)for(u32 i=0;i<n/2;i++){
        s16 p=S.positions[i];u32 cv=S.cvs[i];
        S.positions[i]=S.positions[n-i-1];S.cvs[i]=S.cvs[n-i-1];
        S.positions[n-i-1]=p;S.cvs[n-i-1]=cv;
    }
    S.probe_active=0;S.direction=direction;S.phase=ASCEND;S.leg_started=NOW;
    S.best_index=(s32)n-1;S.last_position=S.positions[n-1];S.up=1;S.down=0;
    S.waiting_reset=0;S.seen=S.frame_seq;S.skip=1;
    if(!predict_braking(n-1))drive(direction*SPEED);
}
static EXTRA(1) void probe_event(u32 t){
    if(t-S.stopped_tick>=300){finish(NO_DATA);return;}
    observe_stability(t);
    if(S.stable_points<3 || (s32)(S.raw_tick-S.stable_tick)<30 || S.verify_seq==S.raw_seq)return;
    S.verify_seq=S.raw_seq;
    u32 cv=S.raw_cv;
    if(!cv || cv>0x1fffffff){finish(BAD_CV);return;}
    u32 k=S.verify_points++;
    if(k<2)return;
    S.cvs[CAPACITY-3+k-2]=cv;
    if(k<4)return;
    u32 a=S.cvs[CAPACITY-3],b=S.cvs[CAPACITY-2],c=S.cvs[CAPACITY-1];
    cv=median3(a,b,c);u32 spread=max(max(mag((s32)a-(s32)b),mag((s32)b-(s32)c)),mag((s32)a-(s32)c));
    S.noise=max(S.noise,spread);
    u32 n=S.samples,i=n;
    if(probe_seen(S.physical)){finish(POSITION_ERROR);return;}
    while(i && S.positions[i-1]>S.physical){S.positions[i]=S.positions[i-1];S.cvs[i]=S.cvs[i-1];i--;}
    S.positions[i]=(s16)S.physical;S.cvs[i]=cv;S.samples=++n;
    S.best_cv=0;
    for(i=0;i<n;i++)if(S.cvs[i]>S.best_cv){S.best_cv=S.cvs[i];S.best_index=(s32)i;}
    /* 各点中位数±该点三帧全极差包含本次三个原始值。
       S.noise是已测点极差的最大值；差值>2*noise要求两侧保守区间分离。
       原6*全极差门槛远大于这个区间条件，实测强双侧峰亦被拒绝。 */
    u32 threshold=max(8,max(S.best_cv/1000,S.noise*2));
    i=(u32)S.best_index;
    if(n>=3){
        if(i && i+1<n && S.best_cv-S.cvs[i-1]>threshold && S.best_cv-S.cvs[i+1]>threshold){
            s32 p=peak_position(),offset=((s32 (*)(void))0x1a502c)();
            if(mag(offset)>127){finish(CONFIG);return;}
            S.probe_active=0;S.refinements=1;S.coarse_peak=p;move_to(p+offset,MOVE_PEAK);return;
        }
        if(!S.refinements && ((i==0 && S.cvs[0]>S.cvs[1] && S.cvs[1]>=S.cvs[2] && S.cvs[0]-S.cvs[2]>threshold) ||
           (i==n-1 && S.cvs[i]>S.cvs[i-1] && S.cvs[i-1]>=S.cvs[i-2] && S.cvs[i]-S.cvs[i-2]>threshold))){
            if(mag(S.physical-S.positions[i])>2){S.probe_active=2;move_to(S.positions[i],MOVE_START);}
            else launch_probe();
            return;
        }
        if(n>=5){finish(WEAK_PEAK);return;}
    }
    s32 target=S.probe_origin+64*S.direction;
    if(n==2){
        u32 baseline=S.cvs[S.positions[0]==S.probe_origin?0:1];
        target=S.probe_origin+(cv>baseline+threshold?128:-64)*S.direction;
    }else if(n>=3){
        target=S.probe_origin+(S.positions[i]<S.probe_origin?-128:128);
        if(probe_seen(target))target=2*S.probe_origin-target;
    }
    probe_move_to(target);
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
    if(predict_braking(n))return;
    int decline=S.down && S.best_cv-cv>=S.noise*6;
    if(S.phase==FINE_SCAN && d2<0 && d3<0 && S.best_cv-cv>=S.noise*6)decline=1;
    /* 已有上升段后第一处明确下降即刹停；不等原来的三段明显越峰。 */
    if(S.phase==ASCEND && S.best_index>=2 && S.best_index==(s32)n-1 &&
       d3<0 && S.best_cv-cv>max(S.best_cv/20,mag(d2)/4) &&
       S.best_cv-S.cvs[0]>max(S.best_cv/10,S.noise*6))decline=1;
    if(!decline)return;
    if(S.phase==PROBE && S.best_index==0){
        if(S.reversals){error(WEAK_PEAK);return;}
        S.reversals++;clear_scan(ASCEND,-S.direction,SPEED);return;
    }
    s32 lo,hi;
    if(!bracket(&lo,&hi))return;
    if(S.phase==PROBE || S.phase==ASCEND){
        S.coarse_peak=S.positions[S.best_index];S.direction=-S.direction;
        /* 从实际停稳点直接朝峰值短扫，取消先跨峰回到远端再重扫的CF行程。 */
        S.fine_end=S.direction>0?hi+64:lo-64;S.fine_start=S.physical;
        move_to(S.physical,MOVE_START);S.stop_pending=2;
    } else if(S.phase==FINE_SCAN){
        s32 p=peak_position();
        /* 镜头加性校准是已知模型输入；不复用原厂方向搜索或自适应重试算法。 */
        s32 offset=((s32 (*)(void))0x1a502c)();
        if(mag(offset)>127){error(CONFIG);return;}
        S.coarse_peak=p;
        move_to(p+offset,MOVE_PEAK);
    }
}
API int af_event(u32 *events){
    u32 state=CAMERA_STATE;
    if(!S.owned){
        if(state<3 || state>6)return 0;
        /* 辅助段覆盖原搜索正文后，任何armed/owned组合都不能回落原搜索。 */
        S.owned=1;S.phase=WAIT_START;finish(BAD_STATE);*events=0;return 1;
    }
    u32 t=NOW,mask=*events;S.calls++;
    if(state==0 || state==7){
        if(S.phase<DONE){if(!S.reason)S.reason=CANCELLED;S.phase=FAILED;}
        S.owned=0;return 0;
    }
    if(state<3)return 0;
    *events=0;
    u32 boundary=S.pending_error==ENDPOINT;
    if(boundary)S.pending_error=0;
    if(state!=3)error(BAD_STATE);
    if(mask&~0x10u){af_error_events=mask;error(mask&0x20000u?CANCELLED:LENS_ERROR);}
    if(S.armed!=2 || !profile())error(CONFIG);
    if(S.phase==DONE || S.phase==FAILED)return 1;
    if(S.phase!=WAIT_START){
        if(t-S.started>=2400)error(TIME_LIMIT);
        if(!S.position_seq || t-S.position_tick>=100)error(NO_DATA);
        if(!position_valid(S.physical))error(TRAVEL_LIMIT);
    }
    if(S.pending_error)finish(S.pending_error);
    if(S.phase>=DONE)return 1;
    if(video_step(t))return 1;
    if(S.pending_error)return 1;
    if(S.phase==WAIT_START){if(t-S.started>=500)finish(NO_DATA);return 1;}
    if(S.configured && (S.roi0!=R32(0x6cc59c)||S.roi1!=R32(0x6cc5a0)||S.rate!=R32(0x6bcb44)))error(CONFIG);
    if(S.pending_error){finish(S.pending_error);return 1;}
    if(boundary){
        if(S.probe_active && !S.reversals){
            S.reversals++;S.direction=-S.direction;move_to(S.origin+64*S.direction,MOVE_START);
        }else if((S.phase==PROBE || S.phase==ASCEND) && !S.reversals){
            S.reversals++;clear_scan(ASCEND,-S.direction,SPEED);
        }else finish(ENDPOINT);
        return 1;
    }
    if(S.cv_profile && V.dirty && t-S.last_full_tick>=80 &&
       (S.phase==PROBE || S.phase==VERIFY || S.phase==FINE_SCAN)){
        S.video_preview=1;video_plan(5,S.command);return 1;
    }
    if(S.phase==PROBE){probe_event(t);return 1;}
    if(S.phase==MOVE_START || S.phase==MOVE_PEAK){
        if(t-S.move_started>=600){finish(TIME_LIMIT);return 1;}
        if(S.stop_pending){
            observe_stability(t);
            if(S.stable_points<3 || t-S.stable_tick<30)return 1;
            if(S.stop_pending==2){
                S.stop_pending=0;S.fine_start=S.physical;clear_scan(FINE_SCAN,S.direction,FINE_SPEED);return 1;
            }
            S.stop_pending=0;S.reply_seen=0;S.position_baseline=S.position_seq;
            trace(S.command_target);real_position(S.command_target);S.send_returns++;return 1;
        }
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
        if(S.phase==MOVE_START){
            if(S.probe_active==2)launch_probe();
            else if(S.probe_active)settle_probe();
            else clear_scan(FINE_SCAN,S.direction,FINE_SPEED);
            return 1;
        }
        if(!S.refinements && !S.probe_active){
            /* 运动扫描的CV/位置没有共同曝光标记。用停稳后的局部双侧测量消除配对偏移。 */
            S.refinements=1;S.probe_active=1;S.probe_origin=S.physical;S.samples=0;S.noise=1;
            S.best_cv=0;S.best_index=-1;S.cv_profile=V.session==S.generation;
            settle_probe();return 1;
        }
        S.phase=VERIFY;S.stopped_tick=t;S.verify_seq=S.raw_seq;S.verify_points=0;
        if(S.cv_profile)video_plan(7,0);return 1;
    }
    if(S.phase==VERIFY){
        if(t-S.stopped_tick>=250){finish(WEAK_PEAK);return 1;}
        if((s32)(S.raw_tick-S.stopped_tick)<50 || S.verify_seq==S.raw_seq)return 1;
        S.verify_seq=S.raw_seq;
        if(t-S.raw_tick>40 || mag(S.physical-S.target)>S.position_tolerance || !S.raw_cv || S.raw_cv>0x1fffffff){S.verify_points=0;return 1;}
        if(S.raw_cv>=S.best_cv-max(S.best_cv/100,S.noise))S.verify_points++;else S.verify_points=0;
        if(S.verify_points>=3)finish(OK);return 1;
    }
    if(S.phase==PROBE && t-S.leg_started>=120 && S.samples>=5 && !S.reversals){
        S.reversals++;clear_scan(ASCEND,-S.direction,SPEED);return 1;
    }
    if(t-S.leg_started>=(S.phase==PROBE?250:700)){finish(TIME_LIMIT);return 1;}
    u32 n=S.frame_consumed,pending=n-S.seen;
    if((s32)pending<=0)goto scan_end;
    /* 16位tag跳过零时，八项实际记录最多跨九个序号。槽内完整序号再校验。 */
    if(pending>9){finish(BAD_COUNT);return 1;}
    while(S.seen!=n){
        u32 seq=S.seen+1;if(!(seq&65535))seq++;
        S.seen=seq;
        struct Frame *p=&S.frames[seq&7];
        u32 stored=p->seq,accepted=p->accepted_seq;publish_barrier();
        u32 cv=p->cv;s32 position=p->position;publish_barrier();
        if(stored!=seq || accepted!=seq || p->seq!=seq){finish(NO_DATA);break;}
        if(S.skip){S.skip--;continue;}
        u32 phase=S.phase;s32 command=S.command;accept(position,cv);
        if(S.pending_error){finish(S.pending_error);break;}
        if(S.command!=command || (S.phase!=phase && !(phase==PROBE && S.phase==ASCEND)))break;
    }
scan_end:
    /* 先消费已到达的最后一份样本，再判行程边界；不能丢弃刚越边界时已成形的峰。 */
    if(S.phase==FINE_SCAN && (S.physical-S.fine_end)*S.direction>0)finish(WEAK_PEAK);
    return 1;
}

#define ENTRY __attribute__((naked,used,target("arm"),section(".text.entry")))
API void af_unexpected_search(void){
    /* 仅四个旧搜索入口调用。辅助区存在时未armed也不能回落执行原搜索正文。 */
    S.owned=1;S.phase=WAIT_START;finish(BAD_STATE);
}
ENTRY void unexpected_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_unexpected_search\npop {r0-r3,r12,lr}\nldr pc,1f\n1:.word 0x19d198");}
ENTRY void dispatch_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nsub r0,fp,#0x94\nbl af_event\ncmp r0,#0\npop {r0-r3,r12,lr}\n"
    "ldrne pc,1f\nmovw r3,#0xb46c\nldr pc,2f\n1:.word 0x19d198\n2:.word 0x19bb98");}
API EXTRA(8) int af_early_event(u32 *events){return S.owned && CAMERA_STATE>=3 && CAMERA_STATE<=6?af_event(events):0;}
ENTRY void early_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nsub r0,fp,#0x94\nbl af_early_event\ncmp r0,#0\npop {r0-r3,r12,lr}\n"
    "ldrne pc,1f\nldr r3,[fp,#-0x94]\nldr pc,2f\n1:.word 0x19d198\n2:.word 0x19b964");}
ENTRY void reset_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmov r0,lr\nbl af_reset_owned\npop {r0-r3,r12,lr}\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a4954");}
ENTRY void speed_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmov r1,lr\nbl af_speed_gate\nstr r0,[sp]\ncmp r0,#65536\npop {r0-r3,r12,lr}\n"
    "bxeq lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a0244");}
ENTRY void position_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_position_gate\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a037c");}
ENTRY void position_observer_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_observe_position\npop {r0-r3,r12,lr}\npush {r4,fp,lr}\nldr pc,1f\n1:.word 0x1a1cdc");}
ENTRY void position_pairer_entry(void){__asm__ volatile(
    "ldr r3,1f\nldr r3,[r3,#40]\ncmp r3,#0\nldrne pc,2f\nmovw r3,#0xcb86\nldr pc,3f\n"
    "1:.word af_state\n2:.word 0x1a22b4\n3:.word 0x1a1fe0");}
ENTRY void cv_observer_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_observe_cv\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxeq lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a1a9c");}
ENTRY void frame_tag_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nldr r0,[fp,#-0x10]\nbl af_tag_frame\ncmp r0,#0\nstrhne r0,[fp,#-0x16]\n"
    "pop {r0-r3,r12,lr}\nmov r3,#0xcc\nstrh r3,[fp,#-0x18]\nldr pc,1f\n1:.word 0x198724");}
ENTRY void position_reply_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nbl af_position_reply\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {r4,r5,fp,lr}\nldr pc,1f\n1:.word 0x1a0ec0");}
ENTRY void near_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmov r0,#1\nbl af_boundary\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a049c");}
ENTRY void far_entry(void){__asm__ volatile(
    "push {r0-r3,r12,lr}\nmvn r0,#0\nbl af_boundary\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a06e8");}
