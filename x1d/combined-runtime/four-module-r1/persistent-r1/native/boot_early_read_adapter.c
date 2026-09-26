/* 固定X1D 1.25.0候选适配器。发布前必须验证原指令、内存归属和缓存同步。
 * 解码阶段只收件；原诊断线程执行内存操作。未编入当前稳定安装包。
 */
#define HBL_BATCH_COMPARE_ONLY 1
#include "boot_batch_mailbox.h"
#include "../build/batch-model/adapter_ranges.h"
struct HblBatchAdapter {
    uint32_t enabled,heap,writeRegion;
    struct HblBatchMailbox mailbox;
};
struct HblBatchAdapter hbl_batch_adapter;
static int inside(uint32_t a,uint32_t start,uint32_t bytes) {
    return !(a&3) && a>=start && (uint64_t)a+4<=(uint64_t)start+bytes;
}
static int allow(void *unused,uint32_t op,uint32_t a,uint32_t v,uint32_t mask) {
    (void)unused;(void)v;(void)mask;
    // Early receiver is strictly compare-only and does not require an AF heap.
    if(op!=1)return 0;
    for(unsigned i=0;i<sizeof(hbl_batch_ranges)/sizeof(hbl_batch_ranges[0]);++i)
        if(inside(a,hbl_batch_ranges[i][0],hbl_batch_ranges[i][1]))return 1;
    return 0;
}
static int get(void *ctx,uint32_t a,uint32_t *v) {(void)ctx;*v=*(volatile uint32_t *)(uintptr_t)a;return 1;}
static int put(void *ctx,uint32_t a,uint32_t v) {(void)ctx;(void)a;(void)v;return 0;}
/* 此签名来自原调用点：四个寄存器参数及两个栈参数，最后一个为控制帧标志。 */
int hbl_batch_decode(void *input,uint32_t bytes,unsigned char *output,void *a3,void *a4,unsigned char *control) {
    typedef int (*Decode)(void *,uint32_t,unsigned char *,void *,void *,unsigned char *);
    int n=((Decode)(uintptr_t)0x23cfa4)(input,bytes,output,a3,a4,control);
    if(n<0 || !control || *control || !__atomic_load_n(&hbl_batch_adapter.enabled,__ATOMIC_ACQUIRE))return n;
    int staged=hbl_batch_stage(&hbl_batch_adapter.mailbox,output,(size_t)n);
    return staged==0?n:staged;
}
void hbl_batch_read_dispatch(const unsigned char *request) {
    unsigned char reply[287]={0};
    const struct HblBatchMemory memory={0,allow,get,put};
    if(__atomic_load_n(&hbl_batch_adapter.enabled,__ATOMIC_ACQUIRE) &&
       hbl_batch_consume(&hbl_batch_adapter.mailbox,&memory,request,reply)) {
        typedef int (*Send)(const unsigned char *);
        if(!((Send)(uintptr_t)0x1e80d0)(reply))__atomic_store_n(&hbl_batch_adapter.enabled,0,__ATOMIC_RELEASE);
        return;
    }
    typedef void (*Original)(const unsigned char *);
    ((Original)(uintptr_t)0x1e1768)(request);
}
