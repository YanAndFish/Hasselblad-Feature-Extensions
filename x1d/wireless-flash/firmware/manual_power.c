/* 独立功率参数候选，绑定 prepared-wltest 的固定输入。
 * 所有可达波形都是 BC 功率包；没有普通 B4 引闪命令接口。
 * 本文件本轮只编译与模拟，不表示已安装或实灯验证。
 */
#include <stdint.h>
#include <stddef.h>
#include "../native/godox_power_wave.h"
#include "godox_power_hashes.h"

#define FN(address,type) ((type)(uintptr_t)((address)|1u))
#define STATE ((volatile uint32_t *)0x2147e0u)
#define RUNS ((HblGodoxPowerRun *)0x215c00u)
#define POWER_MAGIC 0x47505731u
#define POWER_MARKER 0x5852u
#define POWER_CONFIG_BASE 512u
#define POWER_VALUES 405u

typedef struct {
    uint32_t magic, owner, ready, index, expected_hash, busy, sent_count;
} PowerContext;
#define CONTEXT ((volatile PowerContext *)0x217f00u)
_Static_assert(offsetof(PowerContext,expected_hash)==16,"fast checksum offset");
_Static_assert(sizeof(HblGodoxPowerRun)==8,"fixed run layout");

typedef unsigned (*PiCall)(uintptr_t);
typedef unsigned (*PiModeCall)(uintptr_t,unsigned);

static unsigned owned(uintptr_t pi) {
    return CONTEXT->magic==POWER_MAGIC && CONTEXT->owner==pi && STATE[4]==1;
}

static unsigned hold(uintptr_t pi) {
    if (CONTEXT->busy) return 9;
    if (STATE[4]==1) return owned(pi) ? 1 : 9;
    CONTEXT->ready=0;
    unsigned result=FN(0x215f00,PiCall)(pi);
    if (result==1) {
        CONTEXT->magic=POWER_MAGIC;
        CONTEXT->owner=pi;
        CONTEXT->index=POWER_VALUES;
        CONTEXT->expected_hash=0;
        CONTEXT->sent_count=0;
    }
    return result;
}

static unsigned release(uintptr_t pi) {
    if (CONTEXT->busy || (STATE[4]==1 && !owned(pi))) return 9;
    CONTEXT->ready=0;
    unsigned result=FN(0x215fa0,PiCall)(pi);
    if (result==1) {
        CONTEXT->magic=0;
        CONTEXT->owner=0;
        CONTEXT->expected_hash=0;
        CONTEXT->index=POWER_VALUES;
    }
    return result;
}

static unsigned configure(uintptr_t pi,unsigned index) {
    if (!owned(pi) || CONTEXT->busy || index>=POWER_VALUES) return 9;
    CONTEXT->busy=1;
    CONTEXT->ready=0;
    STATE[0]=0; STATE[2]=0;
    CONTEXT->index=index;
    CONTEXT->expected_hash=hbl_power_expected_hashes[index];
    if (!CONTEXT->expected_hash ||
        !hbl_godox_power_runs_encode(RUNS,index/81,index%81)) {
        CONTEXT->busy=0;
        return 12;
    }
    unsigned result=FN(0x214800,PiCall)(pi);
    if (result==1) {
        const uint32_t actual=FN(0x214a00,PiCall)(pi);
        if (actual!=CONTEXT->expected_hash || STATE[1]!=actual || STATE[2]!=1)
            result=13;
    }
    if (result==1) CONTEXT->ready=1;
    else { STATE[0]=0; STATE[2]=0; }
    CONTEXT->busy=0;
    return result;
}

static unsigned send_power(uintptr_t pi) {
    if (!owned(pi) || CONTEXT->busy) return 9;
    if (CONTEXT->ready!=1 || CONTEXT->index>=POWER_VALUES ||
        !CONTEXT->expected_hash ||
        CONTEXT->expected_hash!=hbl_power_expected_hashes[CONTEXT->index] ||
        STATE[0]!=1 || STATE[2]!=1 || STATE[1]!=CONTEXT->expected_hash) return 3;
    CONTEXT->busy=1;
    CONTEXT->ready=0;
    /* 固定原单次射频入口，仅把其期望校验值改为上述真实功率波形值。
     * 驱动返回不等于闪光灯确认接收。失败没有重发。
     */
    const unsigned result=FN(0x216800,PiModeCall)(pi,0);
    if (result==1) { CONTEXT->ready=1; ++CONTEXT->sent_count; }
    CONTEXT->busy=0;
    return result;
}

__attribute__((used)) unsigned hbl_power_dispatch(uintptr_t pi,unsigned selector) {
    switch (selector) {
    case 0: return POWER_MARKER;
    case 15: return owned(pi) && CONTEXT->ready ? STATE[1]&0xffffu : 0;
    case 16: return owned(pi) && CONTEXT->ready ? STATE[1]>>16 : 0;
    case 17: return owned(pi) ? CONTEXT->ready : 0;
    case 18: return owned(pi) && CONTEXT->ready ? CONTEXT->index : 0xffffu;
    case 26: return hold(pi);
    case 27: return release(pi);
    case 48: return send_power(pi);
    default:
        if (selector>=POWER_CONFIG_BASE && selector<POWER_CONFIG_BASE+POWER_VALUES)
            return configure(pi,selector-POWER_CONFIG_BASE);
        /* 拒绝旧模块的所有试闪/试验选择器，也不开放任意寄存器接口。 */
        return 0xfffdu;
    }
}
