#include "../native/boot_batch.h"
#include "../build/boot-data/boot_contract_data.h"
#include "../build/boot-data/af_relocation_data.h"
#include <map>
#include <vector>
#include <string>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cassert>
#undef assert
#define assert(x) do { if(!(x)) {std::fprintf(stderr,"check failed line=%d\n",__LINE__);std::exit(2);} } while(0)

struct Model : HblBootBatchIO {
    bool compareBatch(const HblBootCompare *,size_t) override {return false;}
    bool uploadBatch(uint32_t,const uint32_t *,size_t) override {return false;}
    std::map<uint32_t,uint32_t> mem;
    std::vector<std::pair<uint32_t,uint32_t>> writes;
    std::string stage;
    unsigned requests=0,checkpoints=0,afterFailure=0,sgis=0;
    unsigned failRequest=0,failCheckpoint=0;
    bool failed=false,noAck=false,badAllocation=false,corruptCode=false,factoryVerified=false;
    uint32_t heap=0x39cec0,lastRead=0;
    Model() {
        for(const auto &p:hbl_boot_expected)mem[p.address]=p.value;
        for(const auto &p:hbl_flash_expected)mem[p.address]=p.value;
        for(const auto &g:hbl_boot_guards)mem[g.address]=g.value;
        for(const auto &g:hbl_flash_guards)mem[g.address]=g.value;
        for(uint32_t a=0x2b2800;a<0x2b2840;a+=4)mem[a]=0;
    }
    bool enter() {
        if(failed){++afterFailure;return false;}
        if(++requests==failRequest){failed=true;return false;}
        return true;
    }
    bool version() override {return enter();}
    bool read(uint32_t a,uint32_t *out) override {
        if(!enter())return false;
        lastRead=a;*out=mem[a];return true;
    }
    bool write(uint32_t a,uint32_t v) override {
        assert(factoryVerified);
        if(!enter())return false;
        writes.emplace_back(a,v);mem[a]=v;
        if(a==0x1e2224) {
            for(const auto &h:hbl_bootstrap_hooks)if(a==h.address && v==h.replacement) {
                mem[hbl_boot_control+4]=1;mem[hbl_boot_control+8]=1;
                const uint32_t raw=heap-24,block=32808;
                mem[hbl_boot_request+24]=3;mem[hbl_boot_request+28]=0;
                mem[hbl_boot_request+32]=raw;mem[hbl_boot_request+36]=heap;
                mem[hbl_boot_request+40]=block;mem[hbl_boot_request+44]=500000;
                mem[hbl_boot_request+48]=500000-block;
                mem[raw-8]=0;mem[raw-4]=(block|0x80000000u)^(badAllocation?8u:0u);
            }
        }
        if(a==0xf8f01f00) {
            ++sgis;
            if(noAck){mem[0xf8f01200]=0x8000;return true;}
            const uint32_t cb=mem[0x2a5074],arg=mem[0x2a5078];
            if(cb==0x2b2800) {
                if(mem[cb]==0xe3021026)mem[arg]=0xafaf2026;
                else if(mem[cb]==0xe92d4010)mem[arg+12]=1;
                else {std::fprintf(stderr,"unknown scratch invocation\n");std::abort();}
            } else if(cb==heap+hbl_offset_af_install_probe)mem[arg]=0x314b4341;
            else assert(cb==0x10a2d0 || cb==0x10a310);
        }
        return true;
    }
    bool checkpoint(const char *s,uint32_t,uint32_t,bool) override {
        if(failed){++afterFailure;return false;}
        stage=s;
        if(stage=="factory-verified"){assert(writes.empty());factoryVerified=true;}
        if(++checkpoints==failCheckpoint){failed=true;return false;}
        if(corruptCode && stage=="verify-af")mem[heap]^=1;
        return true;
    }
    bool pause(unsigned) override {return !failed;}
};

int main(int argc,char **argv) {
    if(argc==4 && !std::strcmp(argv[1],"relocate")) {
        uint32_t words[sizeof(hbl_af_words)/4];
        if(!hbl_relocate_af(uint32_t(std::strtoul(argv[2],nullptr,0)),words,sizeof(words)/4))return 3;
        FILE *f=std::fopen(argv[3],"wb");if(!f)return 4;
        bool ok=std::fwrite(words,1,sizeof(words),f)==sizeof(words);std::fclose(f);return ok?0:5;
    }
    unsigned tests=0;
    Model normal;
    bool ok=hbl_load_boot_modules(normal);
    if(!ok){std::fprintf(stderr,"normal failed stage=%s read=%08x writes=%zu requests=%u\n",normal.stage.c_str(),normal.lastRead,normal.writes.size(),normal.requests);return 1;}
    assert(normal.stage=="modules-ready" && normal.mem[hbl_flash_record+4]==1);
    assert(normal.mem[0x2a5074]==0x109304 && normal.mem[0x2a5078]==0x6da728);
    for(uint32_t a=0x2b2800;a<0x2b2840;a+=4)assert(normal.mem[a]==0);
    for(const auto &h:hbl_bootstrap_hooks)assert(normal.mem[h.address]==h.original);
    ++tests;
    // 每个协议边界都注入失败，确认停止且没有请求重发。
    for(unsigned i=1;i<=normal.requests;++i) {
        Model m;m.failRequest=i;
        assert(!hbl_load_boot_modules(m));assert(m.requests==i && !m.afterFailure);++tests;
    }
    // 持久记录失败同样禁止后续设备操作。
    for(unsigned i=1;i<=normal.checkpoints;++i) {
        Model m;m.failCheckpoint=i;
        assert(!hbl_load_boot_modules(m));assert(m.checkpoints==i && !m.afterFailure);++tests;
    }
    Model badFactory;badFactory.mem[hbl_boot_expected[0].address]^=1;
    assert(!hbl_load_boot_modules(badFactory) && badFactory.writes.empty());++tests;
    Model oldSession;oldSession.mem[hbl_bootstrap_base]=0x1234;
    assert(!hbl_load_boot_modules(oldSession) && oldSession.writes.empty());++tests;
    Model previousLoaded;previousLoaded.mem=normal.mem;
    assert(!hbl_load_boot_modules(previousLoaded) && previousLoaded.writes.empty());++tests;
    for(const auto &hook:hbl_flash_hooks) {
        Model partial;partial.mem[hook.address]=hook.replacement;
        assert(!hbl_load_boot_modules(partial) && partial.writes.empty());++tests;
    }
    Model partialBody;partialBody.mem[hbl_flash_base]=0x1234;
    assert(!hbl_load_boot_modules(partialBody) && partialBody.writes.empty());++tests;
    Model badHeap;badHeap.badAllocation=true;
    assert(!hbl_load_boot_modules(badHeap));
    for(const auto &w:badHeap.writes)assert(w.first<badHeap.heap || w.first>=badHeap.heap+32768);++tests;
    Model unknownSGI;unknownSGI.noAck=true;
    assert(!hbl_load_boot_modules(unknownSGI) && unknownSGI.sgis==1);++tests;
    Model badReadback;badReadback.corruptCode=true;
    assert(!hbl_load_boot_modules(badReadback) && badReadback.mem[hbl_boot_control]==0);++tests;
    uint32_t b[sizeof(hbl_af_words)/4];
    for(uint32_t base:{0u,0x100000u,0x39cec1u,0x800000u,0xffffffe0u}) {
        assert(!hbl_relocate_af(base,b,sizeof(b)/4));++tests;
    }
    std::printf("checks=%u hardware-requests=0 normal-requests=%u normal-writes=%zu\n",tests,normal.requests,normal.writes.size());
    return 0;
}
