#include <stdint.h>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <vector>
#include "../build/boot-data/boot_contract_data.h"
int hbl_fast_check_memory(int (*)(void *,uint32_t,uint32_t *),void *);
struct Memory {
    std::map<uint32_t,uint32_t> words;
    std::vector<uint32_t> reads;
    unsigned failAt=0, count=0;
    bool trace=false;
};
static int readWord(void *context,uint32_t address,uint32_t *value) {
    Memory &m=*static_cast<Memory *>(context);
    ++m.count;
    if (m.trace) m.reads.push_back(address);
    if (m.failAt && m.count==m.failAt) return 0;
    auto found=m.words.find(address);
    if (found==m.words.end()) {std::fprintf(stderr,"unexpected address %x\n",address);std::abort();}
    *value=found->second;
    return 1;
}
static void require(bool value) {if(!value) std::abort();}
int main() {
    Memory m;
    for(auto p:hbl_boot_expected) m.words[p.address]=p.value;
    for(auto p:hbl_flash_expected) m.words[p.address]=p.value;
    for(uint32_t a=0x2b2800;a<0x2b2840;a+=4) m.words[a]=0;
    for(uint32_t a=hbl_flash_base;a<hbl_flash_base+sizeof(hbl_flash_words);a+=4) m.words[a]=0;
    const auto exact=m.words;
    for(auto g:hbl_boot_guards) m.words[g.address]=(m.words[g.address]&~g.mask)|g.value;
    for(auto g:hbl_flash_guards) m.words[g.address]=(m.words[g.address]&~g.mask)|g.value;
    m.trace=true;
    require(hbl_fast_check_memory(readWord,&m)==1);
    m.trace=false;
    const unsigned reads=m.count;
    for(auto p:exact) {
        bool found=false;
        for(auto a:m.reads) if(a==p.first) {found=true;break;}
        require(found);
        m.words[p.first]^=1;
        require(hbl_fast_check_memory(readWord,&m)==0);
        m.words[p.first]^=1;
    }
    for(unsigned i=1;i<=reads;++i) {
        m.count=0;m.failAt=i;
        require(hbl_fast_check_memory(readWord,&m)==0);
        require(m.count==i);
    }
    m.failAt=0;
    unsigned masks=0;
    for(auto g:hbl_boot_guards) {
        const uint32_t bit=g.mask & (0u-g.mask);
        m.words[g.address]^=bit;
        require(hbl_fast_check_memory(readWord,&m)==0);
        m.words[g.address]^=bit;
        ++masks;
    }
    for(auto g:hbl_flash_guards) {
        const uint32_t bit=g.mask & (0u-g.mask);
        m.words[g.address]^=bit;
        require(hbl_fast_check_memory(readWord,&m)==0);
        m.words[g.address]^=bit;
        ++masks;
    }
    require(hbl_fast_check_memory(nullptr,&m)==0);
    std::printf("passed: %zu word mutations, %u read failures, %u guard mutations; hardware requests=0\n",exact.size(),reads,masks);
}
