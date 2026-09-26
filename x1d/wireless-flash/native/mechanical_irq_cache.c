/* 官方 X1D 1.25.0 固定 PL 缓存的离线候选核心。
 * 不含设备入口、锁、PCAP 或 USB。调用者仍须实现任务上下文、互斥与缓存一致性。
 * 任意混合态只在完整归一化 SHA 匹配后才允许逆向恢复。
 */
#include <stdint.h>
#include "irq_cache_plan.h"

/* 配置小于 16 MiB，偏移用三个字节；数值仍独立按 32-bit 对齐。 */
static uint32_t plan_offset(uint32_t row) {
  const uint8_t *p=irq_cache_offsets[row];
  return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16);
}

static uint32_t rr(uint32_t x,unsigned n) { return (x>>n)|(x<<(32-n)); }
static const uint32_t k[64]={
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};

static void block(uint32_t h[8],uint32_t w[64]) {
  uint32_t a=h[0],b=h[1],c=h[2],d=h[3],e=h[4],f=h[5],g=h[6],v=h[7];
  for(unsigned i=16;i<64;i++) {
    uint32_t x=w[i-15],y=w[i-2];
    w[i]=w[i-16]+(rr(x,7)^rr(x,18)^(x>>3))+w[i-7]+(rr(y,17)^rr(y,19)^(y>>10));
  }
  for(unsigned i=0;i<64;i++) {
    uint32_t t=v+(rr(e,6)^rr(e,11)^rr(e,25))+((e&f)^(~e&g))+k[i]+w[i];
    uint32_t u=(rr(a,2)^rr(a,13)^rr(a,22))+((a&b)^(a&c)^(b&c));
    v=g;g=f;f=e;e=d+t;d=c;c=b;b=a;a=t+u;
  }
  h[0]+=a;h[1]+=b;h[2]+=c;h[3]+=d;h[4]+=e;h[5]+=f;h[6]+=g;h[7]+=v;
}

/* 返回 0 原厂、1 候选、2 可恢复的混合态、3 未知/损坏。
 * 完整归一化哈希不等于当前内容哈希，明确区分二者的证明目的。
 */
uint32_t mechanical_irq_cache_classify(const volatile uint32_t *image,uint32_t bytes) {
  if(!image || bytes!=IRQ_CACHE_BYTES || ((uintptr_t)image&3)) return 3;
  uint32_t h[8]={0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19};
  uint32_t w[64],row=0,seen_old=0,seen_new=0,bad=0;
  uint32_t next_offset=plan_offset(0);
  const uint32_t words=IRQ_CACHE_BYTES/4;
  const uint32_t padded=(words+17u)&~15u;
  for(uint32_t pos=0;pos<padded;pos+=16) {
    for(unsigned j=0;j<16;j++) {
      uint32_t at=pos+j,x=0;
      if(at<words) {
        x=image[at];
        if(next_offset==at*4) {
          uint32_t old=irq_cache_values[row][0],next=irq_cache_values[row][1];
          if(x==old) seen_old=1; else if(x==next) seen_new=1; else bad=1;
          x=old;row++;next_offset=row<IRQ_CACHE_ROWS?plan_offset(row):0xffffffffu;
        }
        x=__builtin_bswap32(x);
      } else if(at==words) x=0x80000000;
      else if(at==padded-1) x=IRQ_CACHE_BYTES*8;
      w[j]=x;
    }
    block(h,w);
  }
  for(unsigned i=0;i<8;i++) bad|=h[i]^irq_cache_baseline_sha[i];
  if(bad || row!=IRQ_CACHE_ROWS) return 3;
  return seen_new ? (seen_old?2:1) : 0;
}

/* action 1=应用，2=恢复。未知数据无写入；混合态只允许恢复。
 * budget 是离线故障注入及后续任务分段的最多写字数，不是时间上限。
 * 返回 4 表示仍有已识别的混合态；返回 5 表示参数/状态不允许。
 */
uint32_t mechanical_irq_cache_change(volatile uint32_t *image,uint32_t bytes,uint32_t action,uint32_t budget) {
  if(action!=1 && action!=2) return 5;
  uint32_t state=mechanical_irq_cache_classify(image,bytes),used=0;
  if(state==3 || (state==2 && action==1)) return 5;
  for(unsigned i=0;i<IRQ_CACHE_ROWS;i++) {
    uint32_t offset=plan_offset(i)/4,value=irq_cache_values[i][action==1?1:0];
    if(image[offset]!=value) {
      if(used==budget) return 4;
      image[offset]=value;used++;
    }
  }
  state=mechanical_irq_cache_classify(image,bytes);
  return state==(action==1?1u:0u) ? 0u:5u;
}
