/* X1D 1.25.0 候选：在已验证的 SGI 上下文内执行，不分配内存。
 * 主机须先验证本程序、期望正文、描述符及原厂依赖，再一次性调用。
 * 尚未安装；失败保留门控，禁止重入。
 */
#include <stdint.h>
#include "../build/task-cache/contract.h"
struct Request { uint32_t magic,raw,block,session,state,reason; };
#define WORD(a) (*(volatile uint32_t *)(uintptr_t)(a))
static int idle(void) {
    return !(WORD(0x6bb46c)&255) && !(WORD(0x6bb598)&255) &&
        (WORD(0x2adc78)&0xff00)==0x1200 && !(WORD(0x2adc8c)&255);
}
static void sync_range(uint32_t a,uint32_t n) {
    ((void (*)(uint32_t,uint32_t))(uintptr_t)0x10a270)(a,n);
    ((void (*)(uint32_t,uint32_t))(uintptr_t)0x10a354)(a,n);
}
static uint32_t replacement(unsigned i,uint32_t heap) {
    uint32_t a=hooks[i][0],v=hooks[i][2];
    uint32_t target=a+8+(uint32_t)((int32_t)((v&0xffffff)<<8)>>6);
    return (v&0xff000000)|(((target+heap-0x800000-a-8)>>2)&0xffffff);
}
static int identity_valid(uint32_t heap) {
    uint32_t a=heap+IDENTITY,sequence=WORD(a),key=WORD(a+4);
    if(!sequence) {
        if(key)return 0;
        for(unsigned i=8;i<44;i+=4)if(WORD(a+i))return 0;
        return 1;
    }
    if(sequence&1)return 0;
    static const uint32_t keys[]={0x13131,0x13e3e,0x32727,0x14949,0x12323,0x24f4f,0x1532f,0x12f1c};
    static const uint32_t speeds[]={5900,6200,4500,5000,2500,4500,6000,6000};
    uint32_t speed=0;
    for(unsigned i=0;i<8;++i)if(keys[i]==key)speed=speeds[i];
    if(!speed)return 0;
    uint32_t focal=WORD(0x6bcb7c),off=(focal>>8)&255;
    if((((focal>>16)-off)&255)!=(key&255) || (((focal>>24)-off)&255)!=((key>>8)&255))return 0;
    for(unsigned i=0;i<9;++i) {
        uint32_t v=WORD(a+8+4*i);
        if(v!=WORD(0x2adc20+4*i) || (i==((focal&255)?4u:3u) && v!=speed))return 0;
    }
    return WORD(a)==sequence;
}
__attribute__((visibility("default"))) void hbl_af_resident_init(struct Request *r) {
    uint32_t address=(uint32_t)(uintptr_t)r;
    if(address<0x2bacb0+24576 || address>0x6baca0-8192 || (address&31))return;
    uint32_t heap=address-24576;
    if(r->magic!=0x31494641 || !r->session || r->state || r->reason)return;
    r->state=1;
    r->reason=1;
    uint32_t raw=r->raw,block=r->block;
    if(raw<0x2bacb0 || raw>=0x6baca0 || (raw&7) || heap!=((raw+31)&~31u) ||
       (block&7) || block<32808 || (uint64_t)raw-8+block>0x6baca0 ||
       (uint64_t)heap+32768>(uint64_t)raw-8+block || WORD(raw-8) || WORD(raw-4)!=(block|0x80000000u))return;
    r->reason=2;
    if(!idle() || WORD(0x2b37b4) || WORD(0x19b960)!=GATE_BRANCH)return;
    /* 在第一次改动对焦正文前完整核对所有待发布入口。 */
    for(unsigned i=0;i<HOOK_COUNT;++i)if(WORD(hooks[i][0])!=hooks[i][1])return;
    /* 批量通道空闲才允许本次收尾；发送 SGI 的原厂命令与回复路径不改。 */
    if(WORD(0x23acac)!=0xeb01deffu || WORD(0x1e2224)!=0xeb034224u ||
       WORD(0x2b3060) || WORD(0x2b3074) || WORD(0x2a5074)!=heap+8192 || WORD(0x2a5078)!=address)return;
    r->reason=3;
    for(unsigned off=0;off<AF_BYTES;off+=4) {
        uint32_t v=WORD(heap+4096+off);WORD(heap+off)=v;
        if(WORD(heap+off)!=v)return;
    }
    sync_range(heap,AF_BYTES);
    r->reason=4;
    ((void (*)(uint32_t))(uintptr_t)(heap+PROBE))(heap+ACK);
    if(WORD(heap+ACK)!=0x314b4341)return;
    r->reason=5;
    for(unsigned i=0;i<HOOK_COUNT;++i) {
        uint32_t a=hooks[i][0],v=replacement(i,heap);
        if(!idle() || WORD(a)!=hooks[i][1])return;
        WORD(a)=v;
        if(WORD(a)!=v)return;
        sync_range(a&~31u,32);
    }
    r->reason=6;
    for(unsigned off=0;off<AF_BYTES;off+=4) {
        if(off>=IDENTITY && off<IDENTITY+44)continue;
        uint32_t v=off==ACK?0x314b4341:WORD(heap+4096+off);
        if(WORD(heap+off)!=v)return;
    }
    for(unsigned i=0;i<HOOK_COUNT;++i)if(WORD(hooks[i][0])!=replacement(i,heap))return;
    if(!identity_valid(heap) || !idle() || WORD(0x19b960)!=GATE_BRANCH)return;
    r->reason=7;
    WORD(0x2b37b4)=2;
    WORD(0x19b960)=GATE_ORIGINAL;
    sync_range(0x19b960&~31u,32);
    if(WORD(0x2b37b4)!=2 || WORD(0x19b960)!=GATE_ORIGINAL)return;
    r->reason=8;
    /* 运行在已归属堆中，不清除当前执行代码。先恢复解码，再恢复消费者。 */
    WORD(0x23acac)=0xeb0008bc;sync_range(0x23acac&~31u,32);
    if(WORD(0x23acac)!=0xeb0008bc)return;
    WORD(0x1e2224)=0xebfffd4f;sync_range(0x1e2224&~31u,32);
    if(WORD(0x1e2224)!=0xebfffd4f)return;
    for(uint32_t a=0x2b2800;a<0x2b2840;a+=4){WORD(a)=0;if(WORD(a))return;}
    sync_range(0x2b2800,64);
    WORD(0x2a5078)=0x6da728;WORD(0x2a5074)=0x109304;
    if(WORD(0x2a5078)!=0x6da728 || WORD(0x2a5074)!=0x109304)return;
    r->reason=0;r->state=2;
}
