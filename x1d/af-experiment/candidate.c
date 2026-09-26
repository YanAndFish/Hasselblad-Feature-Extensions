/* X1D wedge 1.25.0 / FARM apps 827fa74。临时试用；不宣称量产验证。 */
typedef unsigned int u32;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned char u8;
typedef signed int s32;
#define R32(a) (*(volatile u32 *)(a))
#define R16(a) (*(volatile u16 *)(a))
#define RS16(a) (*(volatile s16 *)(a))
#define R8(a) (*(volatile u8 *)(a))
#define NOW R32(0x6badd0)
#define STATE R8(0x6bb46c)
#define VELOCITY RS16(0x6bb5a0)
#define OLD_VELOCITY RS16(0x6bb5a2)
#define COUNT R16(0x6bc954)
#define CV(i) R32(0x6bb5cc + (i)*4)
#define POS(i) RS16(0x6bbd9c + (i)*2)
enum { OFF, OUT, RETURN, DONE };
enum { OK, EXPIRED, CONFIG_CHANGED, BAD_COUNT, SPEED_CHANGED, DISTANCE,
       TIME_BUDGET, BAD_POSITION, ORIGINAL_EDGE, RESET_OTHER, CV_RANGE };
struct Trace { u32 tick; s32 cmd; s32 measured; u32 returned; };
struct AfState {
    u32 magic, abi, armed, until;
    u32 generation, phase, reason, calls, reversals, confirmations;
    u32 started, physical_set, seen, waiting_reset;
    s32 direction, out_speed, first_physical, anchor_pos, turn_pos, step;
    u32 anchor_cv, turn_cv, noise, points, return_points, return_previous;
    s32 last_pos;
    u32 cv[5], meta[12];
    u32 trace_count, trace_overflow;
    struct Trace trace[24];
    u32 canary;
};
__attribute__((section(".data.state"),used))
volatile struct AfState af_state = { .magic=0x41463552, .abi=1, .canary=0x52463541 };
static u32 maximum(u32 a,u32 b){return a>b?a:b;}
static s32 sign(s32 v){return (v>0)-(v<0);}
static u32 magnitude(s32 v){return v<0?(u32)-v:(u32)v;}
/* 2 为用户明确要求的持续 RAM 试用；每轮 AF 的距离和250 tick预算仍独立生效。 */
static int enabled(void){return af_state.armed==1 || af_state.armed==2;}
static int live(void){return af_state.armed==2 || (af_state.armed==1 && (s32)(af_state.until-NOW)>0);}
static int profile(void){
    return R8(0x2adc79)==18 && R8(0x2adc8c)==0
      && R32(0x2adc2c)==8000 && R32(0x2adc30)==8000 && R32(0x6bc9b0)==8000;
}
static u32 meta_word(u32 i) {
    if(i<8) return R32(0x2b1da8+i*4);
    if(i<10) return R32(0x6cc59c+(i-8)*4);
    if(i==10) return R32(0x2b1da4);
    return R32(0x6bcb44);
}
static void metadata_save(void){for(u32 i=0;i<12;i++)af_state.meta[i]=meta_word(i);}
static int metadata_same(void){
    for(u32 i=0;i<12;i++)if(af_state.meta[i]!=meta_word(i))return 0;
    return 1;
}
static int fallback(u32 why){af_state.reason=why;af_state.phase=OFF;return 0;}
/* 只在一次全新普通AF周期启用。原厂内部复位不重新获得折返预算。 */
void af_reset(u32 caller) {
    af_state.phase=OFF;af_state.reason=RESET_OTHER;
    if(caller!=0x19bbf0 || !live() || !profile())return;
    af_state.generation++;af_state.phase=OUT;af_state.reason=OK;
    af_state.calls=0;af_state.reversals=0;af_state.confirmations=0;
    af_state.started=0;af_state.physical_set=0;af_state.seen=0;
    af_state.waiting_reset=0;af_state.points=0;af_state.return_points=0;
    af_state.step=0;af_state.direction=0;af_state.trace_count=0;af_state.trace_overflow=0;
}
static u32 median3(u32 a,u32 b,u32 c) {
    if(a>b){u32 t=a;a=b;b=t;}if(b>c){u32 t=b;b=c;c=t;}if(a>b)b=a;return b;
}
static int downhill(void) {
    s32 a=(s32)af_state.cv[0],b=(s32)af_state.cv[1],c=(s32)af_state.cv[2];
    s32 d=(s32)af_state.cv[3],e=(s32)af_state.cv[4];
    u32 noise=maximum(2,maximum(af_state.anchor_cv/1000,
        median3(magnitude(a-2*b+c),magnitude(b-2*c+d),magnitude(c-2*d+e))/2));
    af_state.noise=noise;
    return b-c>(s32)(noise*2) && c-d>(s32)(noise*2) && d-e>(s32)(noise*2)
        && (s32)af_state.anchor_cv-e>=(s32)maximum((af_state.anchor_cv+24)/25,noise*6);
}
int af_decide(void) {
    if(af_state.phase!=OUT && af_state.phase!=RETURN)return 0;
    af_state.calls++;
    if(!live())return fallback(EXPIRED);
    if(!profile())return fallback(CONFIG_CHANGED);
    if(STATE!=3)return fallback(RESET_OTHER);
    if(R8(0x6bb59c)||R8(0x6bb59d))return fallback(ORIGINAL_EDGE);
    u32 n=COUNT,t=NOW; s32 v=VELOCITY, physical=RS16(0x6bb5b4);
    if(n>500)return fallback(BAD_COUNT);
    if(!v || magnitude(v)>8000)return fallback(SPEED_CHANGED);
    if(!af_state.physical_set) {
        af_state.physical_set=1;af_state.first_physical=physical;
        af_state.started=t;af_state.direction=sign(v);af_state.out_speed=v;
        metadata_save();
    }
    if(!metadata_same())return fallback(CONFIG_CHANGED);
    if(t-af_state.started>=250)return fallback(TIME_BUDGET);
    if(af_state.step && magnitude(physical-af_state.first_physical)>(u32)af_state.step*8)
        return fallback(DISTANCE);
    if(af_state.phase==OUT && v!=af_state.out_speed)return fallback(SPEED_CHANGED);
    if(af_state.phase==RETURN) {
        if(sign(v)!=-af_state.direction)return fallback(SPEED_CHANGED);
        if(af_state.waiting_reset) {
            if(sign(OLD_VELOCITY)!=sign(v))return 1;
            af_state.waiting_reset=0;af_state.seen=0;
        }
    }
    if(n<af_state.seen)return fallback(BAD_COUNT);
    /* 单次最多处理原厂500点数组，不读尚未接受的样本。 */
    for(u32 i=af_state.seen;i<n;i++) {
        u32 cv=CV(i);s32 p=POS(i);af_state.seen=i+1;
        if(!cv || cv>0x1fffffff)return fallback(CV_RANGE);
        if(af_state.phase==OUT) {
            if(!af_state.points) {
                af_state.anchor_pos=p;af_state.anchor_cv=cv;
                af_state.cv[0]=cv;af_state.points=1;af_state.last_pos=p;continue;
            }
            s32 travel=(p-af_state.last_pos)*af_state.direction;
            if(travel<0)return fallback(BAD_POSITION);
            if(!travel)continue;
            if(!af_state.step)af_state.step=travel;
            if(travel<af_state.step)continue;
            if(magnitude(p-af_state.anchor_pos)>(u32)af_state.step*8)return fallback(DISTANCE);
            af_state.last_pos=p;
            if(af_state.points<5)af_state.cv[af_state.points++]=cv;
            else { for(u32 k=0;k<4;k++)af_state.cv[k]=af_state.cv[k+1];af_state.cv[4]=cv; }
            if(af_state.points==5) {
                if(!downhill())continue;
                af_state.turn_pos=p;af_state.turn_cv=cv;af_state.started=t;
                af_state.return_points=0;af_state.waiting_reset=1;
                af_state.phase=RETURN;af_state.reversals++;
                ((void (*)(s32))0x1a0240)(-v);
                return 1;
            }
        } else {
            s32 toward=(af_state.last_pos-p)*af_state.direction;
            if(toward<=0)continue;
            if((u32)toward<(u32)af_state.step)continue;
            if((p-af_state.anchor_pos)*af_state.direction < -af_state.step)
                return fallback(DISTANCE);
            af_state.last_pos=p;
            if(af_state.return_points && cv>af_state.return_previous+af_state.noise*2)
                af_state.return_points++;
            else af_state.return_points=1;
            af_state.return_previous=cv;
            u32 recovery=maximum(af_state.anchor_cv/50,af_state.noise*3);
            if(af_state.return_points>=3 && cv>=af_state.anchor_cv-recovery
              && cv>=af_state.turn_cv+af_state.noise*6
              && magnitude(p-af_state.anchor_pos)<=(u32)af_state.step) {
                af_state.phase=DONE;af_state.confirmations++;
                R8(0x6bb5c0)=0;
                if(v>0)R8(0x6bb59c)=1;else R8(0x6bb59d)=1;
                ((void (*)(u32))0x1a4890)(0x20);
                return 1;
            }
        }
    }
    return af_state.phase==RETURN;
}
/* 仅此原厂0xcd发送调用点被替换；参数与原有队列调用保持一致。
   returned表示原厂发送函数返回，不能解释为镜头确认或合焦。 */
u32 af_send(const u8 *message) {
    s32 cmd=(s16)((u32)message[4]|((u32)message[5]<<8));
    u32 index=af_state.trace_count;
    int record=enabled() && index<24 &&
        message[0]==0xcd && message[1]==0 && message[2]==1 && message[3]==3;
    if(record) {
        af_state.trace[index].tick=NOW;af_state.trace[index].cmd=cmd;
        af_state.trace[index].measured=(s32)R32(0x6bb5a4);
        af_state.trace[index].returned=0;af_state.trace_count=index+1;
    } else if(enabled() && index>=24)af_state.trace_overflow++;
    u32 result=((u32 (*)(const u8 *))0x1e80d0)(message);
    if(record)af_state.trace[index].returned=1;
    return result;
}
__attribute__((naked,used,section(".text.entry")))
void state3_entry(void) {
    __asm__ volatile("push {r0-r3,r12,lr}\nbl af_decide\ncmp r0,#0\npop {r0-r3,r12,lr}\nbxne lr\npush {r4,fp,lr}\nldr pc,1f\n1:.word 0x19d1a0");
}
__attribute__((naked,used,section(".text.entry")))
void reset_entry(void) {
    __asm__ volatile("push {r0-r3,r12,lr}\nmov r0,lr\nbl af_reset\npop {r0-r3,r12,lr}\npush {fp,lr}\nldr pc,1f\n1:.word 0x1a4954");
}
