/* 正式功率/同步候选：两个发送入口严格检查当前波形类型。
 * 仅持有本模块 MAC 所有权时可生成与发送；失败不自动重发。
 */
#include <stdint.h>
#include <stddef.h>
#include "../native/godox_formal_wave.h"
#define FN(a,t) ((t)(uintptr_t)((a)|1u))
#define STATE ((volatile uint32_t *)0x2147e0u)
#define RUNS ((HblGodoxPowerRun *)0x215c00u)
#define MAGIC 0x47464632u
typedef struct { uint32_t magic,owner,ready,index,expected,busy,sent,channel,id,chanspec; } Context;
#define CTX ((volatile Context *)0x217f00u)
_Static_assert(offsetof(Context,expected)==16,"fast expected hash offset");
_Static_assert(offsetof(Context,chanspec)==36,"fast channel guard offset");
typedef unsigned (*PiCall)(uintptr_t);
typedef unsigned (*PiMode)(uintptr_t,unsigned);

static unsigned owned(uintptr_t pi) { return CTX->magic==MAGIC && CTX->owner==pi && STATE[4]==1; }
static unsigned hold(uintptr_t pi) {
    if (CTX->busy) return 9;
    if (STATE[4]==1) return owned(pi) ? 1 : 9;
    CTX->ready=0;
    unsigned result=FN(0x215f00,PiCall)(pi);
    if (result==1) {
        CTX->magic=MAGIC; CTX->owner=pi; CTX->index=HBL_FORMAL_WAVES;
        CTX->expected=0; CTX->sent=0;
        CTX->channel=5; CTX->id=5; CTX->chanspec=hbl_formal_chanspec(5);
    }
    return result;
}
static unsigned release(uintptr_t pi) {
    if (CTX->busy || (STATE[4]==1 && !owned(pi))) return 9;
    CTX->ready=0;
    unsigned result=FN(0x215fa0,PiCall)(pi);
    if (result==1) {
        CTX->magic=0; CTX->owner=0; CTX->index=HBL_FORMAL_WAVES; CTX->expected=0;
    }
    return result;
}
static unsigned prepare(uintptr_t pi,unsigned index) {
    if (!owned(pi) || CTX->busy || index>=HBL_FORMAL_WAVES) return 9;
    CTX->busy=1; CTX->ready=0; CTX->index=index;
    STATE[0]=0; STATE[2]=0; CTX->expected=0;
    uint32_t expected=0;
    if (!hbl_formal_runs_config(RUNS,index,CTX->channel,CTX->id) ||
        !hbl_formal_wave_hash(&expected,index,CTX->channel,CTX->id,(const uint32_t *)0x214c00u)) {
        CTX->busy=0; return 12;
    }
    CTX->expected=expected;
    unsigned result=FN(0x214800,PiCall)(pi);
    if (result==1) {
        const unsigned actual=FN(0x214a00,PiCall)(pi);
        if (actual!=CTX->expected || STATE[1]!=actual || STATE[2]!=1) result=13;
    }
    if (result==1) CTX->ready=1;
    else { STATE[0]=0; STATE[2]=0; }
    CTX->busy=0;
    return result;
}
static unsigned send(uintptr_t pi,unsigned fire) {
    if (!owned(pi) || CTX->busy) return 9;
    if (CTX->ready!=1 || CTX->index>=HBL_FORMAL_WAVES ||
        (CTX->index==HBL_FORMAL_FIRE_INDEX)!=fire || !CTX->expected ||
        !hbl_formal_config_valid(CTX->channel,CTX->id) || CTX->chanspec!=hbl_formal_chanspec(CTX->channel) ||
        STATE[0]!=1 || STATE[2]!=1 || STATE[1]!=CTX->expected) return 3;
    CTX->busy=1; CTX->ready=0;
    // 原逐次 PHY 准备、500 us 等待与清理，和已实测逐次模式一致。
    const unsigned result=FN(0x216800,PiMode)(pi,0);
    if (result==1) { CTX->ready=1; ++CTX->sent; }
    CTX->busy=0;
    return result;
}
static unsigned configure(uintptr_t pi,unsigned channel,unsigned id) {
    if (!owned(pi) || CTX->busy || !hbl_formal_config_valid(channel,id)) return 9;
    CTX->ready=0; CTX->expected=0; CTX->index=HBL_FORMAL_WAVES;
    STATE[0]=0; STATE[2]=0;
    const unsigned chanspec=hbl_formal_chanspec(channel);
    if (*(volatile uint16_t *)(pi+0x10e)!=chanspec) return 4;
    CTX->channel=channel; CTX->id=id; CTX->chanspec=chanspec;
    return 1;
}
__attribute__((used)) unsigned hbl_formal_dispatch(uintptr_t pi,unsigned selector) {
    switch (selector) {
    case 0: return 0x5854;
    case 14: return prepare(pi,HBL_FORMAL_FIRE_INDEX);
    case 15: return owned(pi) && CTX->ready ? STATE[1]&0xffffu : 0;
    case 16: return owned(pi) && CTX->ready ? STATE[1]>>16 : 0;
    case 17: return owned(pi) ? CTX->ready : 0;
    case 18: return owned(pi) && CTX->ready ? CTX->index : 0xffffu;
    case 19: return owned(pi) ? CTX->channel : 0;
    case 20: return owned(pi) ? CTX->id : 0xffffu;
    case 26: return hold(pi);
    case 27: return release(pi);
    case 40: return send(pi,1);
    case 48: return send(pi,0);
    default:
        if (selector>=512 && selector<512+HBL_FORMAL_CONTROL_WAVES) return prepare(pi,selector-512);
        if (selector>=HBL_FORMAL_CONFIG_BASE && selector<HBL_FORMAL_CONFIG_BASE+HBL_FORMAL_CONFIG_COUNT) {
            const unsigned value=selector-HBL_FORMAL_CONFIG_BASE;
            return configure(pi,value/100+1,value%100);
        }
        return 0xfffdu;
    }
}
