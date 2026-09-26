/* X1D 1.25.0 离线微型引导候选；尚未安装。
 * 只顺序写固定接收器暂存区，不执行上传内容，不改对焦入口。
 * 入口必须位于已通过原厂 CRC16 的外层调用链中。
 */
#include <stdint.h>
struct Seed { uint32_t nonce,next,status,failed; };
struct Seed hbl_seed;
static uint32_t word(const unsigned char *p) {
    return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;
}
int hbl_seed_decode(void *input,uint32_t bytes,unsigned char *out,void *a3,void *a4,unsigned char *control) {
    typedef int (*Decode)(void *,uint32_t,unsigned char *,void *,void *,unsigned char *);
    int n=((Decode)(uintptr_t)0x23cfa4)(input,bytes,out,a3,a4,control);
    if(n<16 || !control || *control || word(out)!=0x010500f4 || word(out+4)!=0x31444553)return n;
    /* 采用独立固定格式，普通原厂消息不进入此分支。 */
    uint32_t offset=word(out+12),count=(uint32_t)(n-16);
    if(hbl_seed.failed || !hbl_seed.nonce || word(out+8)!=hbl_seed.nonce ||
       offset!=hbl_seed.next || !count || count>240 || (count&3) || offset>2776 || count>2776-offset) {
        hbl_seed.failed=1;hbl_seed.status=0xffffffff;
    } else {
        for(uint32_t i=0;i<count;i+=4) {
            volatile uint32_t *dest=(volatile uint32_t *)(uintptr_t)(0x2b2880+offset+i);
            uint32_t value=word(out+16+i);*dest=value;
            if(*dest!=value){hbl_seed.failed=1;hbl_seed.status=0xffffffff;break;}
        }
        if(!hbl_seed.failed){hbl_seed.next=offset+count;hbl_seed.status=offset+count;}
    }
    /* 原 F4 线程只读取本次累计状态；没有自定义回调或额外消息队列。 */
    uint32_t address=(uint32_t)(uintptr_t)&hbl_seed.status;
    out[4]=(unsigned char)address;out[5]=(unsigned char)(address>>8);
    out[6]=(unsigned char)(address>>16);out[7]=(unsigned char)(address>>24);
    return 8;
}
