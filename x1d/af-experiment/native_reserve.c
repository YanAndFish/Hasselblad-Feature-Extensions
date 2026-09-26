/* 固定 FARM 1.25.0 的独立内存申请原型。只可在原厂 AF 任务 idle 分发点调用。 */
typedef unsigned int u32;
#define R32(a) (*(volatile u32 *)(a))
#define R8(a) (*(volatile unsigned char *)(a))
enum { NR_REQUEST=1,NR_RUNNING=2,NR_READY=3,NR_REJECTED=4 };
enum { NR_OK=0,NR_CONTEXT=1,NR_FORMAT=2,NR_HEAP=3,NR_SPACE=4,NR_RESULT=5 };
struct NrRequest {
    u32 magic,abi,sequence,payload_bytes,minimum_remaining,checksum,status;
    u32 reason,raw_pointer,payload_base,allocated_bytes,free_before,free_after;
};
static u32 sum(const struct NrRequest *r){
    return r->magic^r->abi^r->sequence^r->payload_bytes^r->minimum_remaining^0x6c871ae5u;
}
static void barrier(void){__asm__ volatile("dmb sy":::"memory");}
static void finish(volatile struct NrRequest *r,u32 status,u32 reason){
    r->reason=reason;barrier();r->status=status;barrier();
}
__attribute__((section(".text.nr_api"))) void nr_reserve(volatile struct NrRequest *r){
    if(r->status!=NR_REQUEST)return;
    u32 cpsr;__asm__ volatile("mrs %0,cpsr":"=r"(cpsr));
    if((cpsr&31)!=31 || !R32(0x6bb470) || R32(0x6baccc)!=R32(0x6bb470) ||
       R8(0x6bb46c)!=0){finish(r,NR_REJECTED,NR_CONTEXT);return;}
    struct NrRequest input=*r;
    if(input.magic!=0x31524e41 || input.abi!=1 || !input.sequence ||
       input.payload_bytes<4096 || input.payload_bytes>32768 ||
       input.minimum_remaining<65536 || input.minimum_remaining>0x200000 ||
       input.checksum!=sum(&input)) {finish(r,NR_REJECTED,NR_FORMAT);return;}
    /* 申请包括 32-byte 对齐余量，原厂分配器另加 8-byte 头并向 8-byte 对齐。 */
    u32 requested=input.payload_bytes+31,needed=(requested+8+7)&~7u;
    r->status=NR_RUNNING;barrier();
    ((void(*)(void))0x188370)();
    u32 end=R32(0x6bacb0),node=R32(0x6baca8),total=0,largest=0,previous=0x2baca8;
    u32 valid=end==0x6baca0 && R32(0x6bacbc)==0x80000000 && R32(0x6bacac)==0;
    u32 i=0;
    while(valid && node!=end && i++<1024){
        if(node<previous || node>=end || (node&7)){valid=0;break;}
        u32 next=R32(node),size=R32(node+4);
        if(size<16 || (size&7) || size>end-node || next<node+size || next>end || (next&7)){
            valid=0;break;
        }
        total+=size;if(size>largest)largest=size;previous=node+size;node=next;
    }
    if(!valid || node!=end || R32(end)!=0 || R32(end+4)!=0 || total!=R32(0x6bacb4)){
        finish(r,NR_REJECTED,NR_HEAP);
    } else if(largest<needed || total<needed+input.minimum_remaining){
        r->free_before=total;finish(r,NR_REJECTED,NR_SPACE);
    } else {
        r->free_before=total;
        u32 raw=((u32(*)(u32))0x184a60)(requested);
        r->raw_pointer=raw;r->free_after=R32(0x6bacb4);
        if(raw<0x2bacb0 || raw>=end || (raw&7) || R32(raw-8)!=0 ||
           !(R32(raw-4)&0x80000000))finish(r,NR_REJECTED,NR_RESULT);
        else {
            u32 bytes=R32(raw-4)&0x7fffffffu,base=(raw+31)&~31u;
            r->allocated_bytes=bytes;r->payload_base=base;
            if(bytes<needed || bytes>end-(raw-8) || base+input.payload_bytes>raw-8+bytes)
                finish(r,NR_REJECTED,NR_RESULT);
            else finish(r,NR_READY,NR_OK);
        }
    }
    /* READY 在可能重新调度之前发布；重复唤醒不会重复申请。此原型不释放存活代码。 */
    ((void(*)(void))0x188424)();
}
