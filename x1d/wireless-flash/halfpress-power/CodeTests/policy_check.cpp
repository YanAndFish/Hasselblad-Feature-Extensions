#ifdef NDEBUG
#undef NDEBUG
#endif
#include <initializer_list>
#include "formal_policy.h"
#include <cassert>
#include <cstdio>
using P=FormalPolicy;
static unsigned power(P &p,uint64_t &now) {
 unsigned count=0;
 for(unsigned i=0;i<150;i++) {
  auto c=p.next(++now);if(c.action==P::None)return count;
  assert(c.action!=P::Fire);count+=c.action==P::Power;p.complete(c.action,true,++now);
 }
 assert(false);return 0;
}
int main(){
 for(unsigned es=0;es<2;es++)for(unsigned mask: {1u,31u,65535u}) {
  P p;uint64_t now=1000000;p.shutterPower=false;p.halfPressPower=true;
  P::Group groups[HBL_FORMAL_GROUPS]={};groups[0].active=1;
  assert(p.setOptions(1,1,1,++now));power(p,now);
  assert(p.flush(1,250000,es,groups,++now,nullptr,true,mask));
  assert(!p.shotActive);unsigned expected=0;for(unsigned n=mask;n;n>>=1)expected+=n&1;
  assert(power(p,now)==expected);assert(!p.shotActive);
  assert(p.queueSync(1,250000,es,++now));assert(p.shotActive);assert(power(p,now)==0);
  assert(p.endShot(1,++now));assert(p.flush(2,250000,es,groups,++now));assert(power(p,now)==0);
  assert(p.endShot(2,++now));assert(p.flush(3,250000,es,groups,++now,nullptr,true,mask));
  assert(p.endShot(3,++now));assert(power(p,now)==0);
 }
 // 关闭能力时拒绝半按请求；正常同步仍不发送功率。
 P p;uint64_t now=1000000;p.shutterPower=false;P::Group groups[HBL_FORMAL_GROUPS]={};
 assert(!p.flush(1,250000,true,groups,++now,nullptr,true,1));
 // 快速全按：未完成发送前的事件不能变成迟到闪光。
 P q;q.shutterPower=false;q.halfPressPower=true;groups[0].active=1;
 assert(q.setOptions(1,1,1,++now));power(q,now);
 assert(q.flush(1,250000,true,groups,++now,nullptr,true,31));
 assert(q.queueSync(1,250000,true,++now));
 HblFarmSync e={HBL_SYNC_MAGIC,3,1,7,0,HBL_SYNC_STATUS_BIT,1,0,1,250000,0};
 uint64_t at=++now;assert(!q.electronicSample(1,e,at*1000,++now));
 assert(power(q,now)==5);assert(q.next(++now).action==P::None);
 puts("halfpress policy modes, masks, cancellation, no full-press power, early-sync checks passed");
}
