#include "../build/block-write/boot_batch_wire.h"
#include <cassert>
#include <vector>
#include <cstdio>
struct Memory {
 uint32_t words[60]={};unsigned writes=0,reads=0;
 int deny=-1,failWrite=-1,failRead=-1,corrupt=-1;
 static int allow(void *p,uint32_t op,uint32_t a,uint32_t,uint32_t mask){
  auto &m=*static_cast<Memory *>(p);
  return op==2 && a>=0x400000 && a<0x4000f0 && mask==~0u && int((a-0x400000)/4)!=m.deny;
 }
 static int put(void *p,uint32_t a,uint32_t v){
  auto &m=*static_cast<Memory *>(p);assert(!m.reads);
  unsigned i=(a-0x400000)/4;++m.writes;
  if(int(i)==m.failWrite)return 0;
  m.words[i]=v;return 1;
 }
 static int get(void *p,uint32_t a,uint32_t *v){
  auto &m=*static_cast<Memory *>(p);assert(m.writes==60);
  unsigned i=(a-0x400000)/4;++m.reads;
  if(int(i)==m.failRead)return 0;
  *v=m.words[i]^(int(i)==m.corrupt?1:0);return 1;
 }
};
int main(){
 std::vector<unsigned char> packet;
 for(uint32_t v:{0x31424248u,42u,0u,2u,60u,0x400000u,0u})for(unsigned i=0;i<4;++i)packet.push_back((v>>(i*8))&255);
 for(unsigned n=0;n<60;++n)for(unsigned i=0;i<4;++i)packet.push_back(((n+1)>>(i*8))&255);
 unsigned checks=0;
 for(int mode=0;mode<5;++mode)for(int at=0;at<(mode?60:1);++at){
  Memory mem;HblBatchState state={42,0,0};
  if(mode==1)mem.deny=at;if(mode==2)mem.failWrite=at;if(mode==3)mem.failRead=at;if(mode==4)mem.corrupt=at;
  HblBatchMemory api={&mem,Memory::allow,Memory::get,Memory::put};
  int result=hbl_batch_execute(&state,&api,packet.data(),packet.size());
  if(!mode){assert(!result && state.sequence==1 && !state.failed && mem.writes==60 && mem.reads==60);}
  else {
   assert(result && state.failed && state.sequence==0);
   if(mode==1)assert(!mem.writes && !mem.reads);
   if(mode==2)assert(mem.writes==unsigned(at+1) && !mem.reads);
   if(mode>=3)assert(mem.writes==60 && mem.reads==unsigned(at+1));
   unsigned w=mem.writes,r=mem.reads;
   assert(hbl_batch_execute(&state,&api,packet.data(),packet.size()) && mem.writes==w && mem.reads==r);
  }
  ++checks;
 }
 std::printf("block-write checks=%u hardware=0\n",checks);
}
