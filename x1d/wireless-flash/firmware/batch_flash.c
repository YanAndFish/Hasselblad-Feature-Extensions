/* 固定 X1D WLTEST 候选：一次执行已提交的参数批次。
 * 当前采样率、每段波形和短引闪入口不变；这是芯片本地分段播放，
 * 不是未经验证的超大模板 RAM 连续播放。 */
#define hbl_formal_dispatch hbl_single_dispatch
#include "formal_flash.c"
#undef hbl_formal_dispatch

enum { BATCH_BEGIN=12000, BATCH_COMMIT=12001, BATCH_SEND=12002,
       BATCH_STATUS=12003, BATCH_ITEM=16384 };
typedef struct {
    uint32_t magic, staging, committed, running, mask, pendingMask;
    uint16_t values[16], pending[16];
} BatchContext;
#define BCTX ((volatile BatchContext *)0x217f40u)
#define BATCH_MAGIC 0x42415431u
_Static_assert(0x40+sizeof(BatchContext)<=0x100,"batch context overlaps heap");

static unsigned batch_send(uintptr_t pi) {
    if (!owned(pi) || CTX->busy || BCTX->magic!=BATCH_MAGIC ||
        !BCTX->committed || BCTX->staging || BCTX->running) return 9;
    BCTX->running=1;
    unsigned result=1;
    for (unsigned group=0;group<16;++group) {
        if (!(BCTX->mask&(1u<<group))) continue;
        unsigned value=BCTX->values[group];
        if (value>=HBL_FORMAL_VALUES) { result=12;break; }
        result=prepare(pi,group*HBL_FORMAL_VALUES+value);
        if (result!=1) break;
        result=send(pi,0);
        if (result!=1) break;
    }
    /* 失败不重发；仍尝试恢复短引闪波形，失败结果不能被恢复成功覆盖。 */
    unsigned restored=prepare(pi,HBL_FORMAL_FIRE_INDEX);
    if (result==1) result=restored;
    if (result!=1) CTX->ready=0;
    BCTX->running=0;
    return result;
}

__attribute__((used)) unsigned hbl_formal_dispatch(uintptr_t pi,unsigned selector) {
    if (selector==0) return 0x5855;
    if (BCTX->running) return 9;
    if (selector==BATCH_STATUS) return owned(pi) && BCTX->magic==BATCH_MAGIC && BCTX->committed && !BCTX->staging;
    if (selector==BATCH_SEND) return batch_send(pi);
    if (selector==BATCH_BEGIN) {
        if (!owned(pi) || CTX->busy) return 9;
        BCTX->magic=BATCH_MAGIC;BCTX->staging=1;BCTX->committed=0;
        BCTX->pendingMask=0;return 1;
    }
    if (selector==BATCH_COMMIT) {
        if (!owned(pi) || CTX->busy || BCTX->magic!=BATCH_MAGIC || !BCTX->staging) return 9;
        for(unsigned i=0;i<16;++i) BCTX->values[i]=BCTX->pending[i];
        BCTX->mask=BCTX->pendingMask;BCTX->staging=0;BCTX->committed=1;return 1;
    }
    if (selector>=BATCH_ITEM && selector<BATCH_ITEM+HBL_FORMAL_POWER_WAVES) {
        if (!owned(pi) || CTX->busy || BCTX->magic!=BATCH_MAGIC || !BCTX->staging) return 9;
        unsigned index=selector-BATCH_ITEM,group=index/HBL_FORMAL_VALUES;
        BCTX->pending[group]=index%HBL_FORMAL_VALUES;
        BCTX->pendingMask|=1u<<group;return 1;
    }
    if (selector==26 || selector==27 ||
        (selector>=HBL_FORMAL_CONFIG_BASE && selector<HBL_FORMAL_CONFIG_BASE+HBL_FORMAL_CONFIG_COUNT)) {
        BCTX->committed=0;BCTX->staging=0;BCTX->magic=0;
    }
    return hbl_single_dispatch(pi,selector);
}
