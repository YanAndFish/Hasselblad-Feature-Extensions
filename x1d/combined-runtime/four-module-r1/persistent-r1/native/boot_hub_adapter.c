/* 固定X1D 1.25.0候选适配器。发布前必须验证原指令、内存归属和缓存同步。
 * 解码阶段只收件；原诊断线程执行内存操作。未编入当前稳定安装包。
 */
#include "../build/task-cache/boot_batch_mailbox.h"
#define HBL_BATCH_AF_BYTES 2976u
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
    uint32_t heap=hbl_batch_adapter.heap;
    int owned=!(heap%32) && heap>=0x2bacb0 && heap<=0x6baca0-32768;
    // 默认 heap=0、writeRegion=0，仅允许固定原厂区比较。
    // 主装载器完成原厂分配及归属核对后，才发布 AF 堆和写入阶段。
    if(op==3) {
        if(a==0x2b3400 && v==960)return 1;
        if(v==32 && (a==(0x19b960&~31u) || a==(0x1e2224&~31u)))return 1;
        if(owned && a==heap+8192 && v && !(v&3) && v<=2200)return 1;
        return 0;
    }
    if(op==2 && hbl_batch_adapter.writeRegion==3)return inside(a,0x2b3400,976);
    if(op==2)return owned && hbl_batch_adapter.writeRegion==1 && inside(a,heap,HBL_BATCH_AF_BYTES);
    return 0;
}
static int get(void *ctx,uint32_t a,uint32_t *v) {(void)ctx;*v=*(volatile uint32_t *)(uintptr_t)a;return 1;}
static int put(void *ctx,uint32_t a,uint32_t v) {(void)ctx;*(volatile uint32_t *)(uintptr_t)a=v;return 1;}
static int sync_memory(void *ctx,uint32_t a,uint32_t n) {
    (void)ctx;
    ((void (*)(uint32_t,uint32_t))(uintptr_t)0x10a270)(a,n);
    ((void (*)(uint32_t,uint32_t))(uintptr_t)0x10a354)(a,n);
    return 1;
}
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
    const struct HblBatchMemory memory={0,allow,get,put,sync_memory};
    if(__atomic_load_n(&hbl_batch_adapter.enabled,__ATOMIC_ACQUIRE) &&
       hbl_batch_consume(&hbl_batch_adapter.mailbox,&memory,request,reply)) {
        typedef int (*Send)(const unsigned char *);
        if(!((Send)(uintptr_t)0x1e80d0)(reply))__atomic_store_n(&hbl_batch_adapter.enabled,0,__ATOMIC_RELEASE);
        return;
    }
    typedef void (*Original)(const unsigned char *);
    ((Original)(uintptr_t)0x1e1768)(request);
}

/* 仅在微型引导器完成本镜像缓存同步后调用；入口切换留在分块镜像。 */
static uint32_t call_branch(uint32_t a,uintptr_t target) {
    return 0xeb000000u|(((uint32_t)target-a-8)/4&0xffffffu);
}
int hbl_batch_activate(uint32_t nonce) {
    if(!nonce || hbl_batch_adapter.enabled!=1 || hbl_batch_adapter.mailbox.state.session!=nonce ||
       hbl_batch_adapter.mailbox.slot || hbl_batch_adapter.mailbox.state.failed ||
       *(volatile uint32_t *)0x1e2224!=0xebfffd4f)return 0;
    uint32_t v=call_branch(0x1e2224,(uintptr_t)hbl_batch_read_dispatch);
    *(volatile uint32_t *)0x1e2224=v;
    if(*(volatile uint32_t *)0x1e2224!=v)return 0;
    sync_memory(0,0x1e2224&~31u,32);
    v=call_branch(0x23acac,(uintptr_t)hbl_batch_decode);
    *(volatile uint32_t *)0x23acac=v;
    if(*(volatile uint32_t *)0x23acac!=v)return 0;
    sync_memory(0,0x23acac&~31u,32);
    return 1;
}
