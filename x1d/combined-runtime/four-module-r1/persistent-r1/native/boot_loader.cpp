/* 仅固定 X1D 1.25.0 首次装载；每次进程生命周期只允许调用一次。 */
#include "boot_batch.h"
#include "../build/batch-model/adapter_data.h"
#include "../build/boot-data/boot_contract_data.h"
#include "../build/boot-data/af_relocation_data.h"
#include <cstring>
#include <initializer_list>

namespace {
constexpr uint32_t scratch=0x2b2800,desc=0x2b2820,cb=0x2a5074,arg=0x2a5078;
constexpr uint32_t origCB=0x109304,origARG=0x6da728,noop=0x1009d4;
constexpr uint32_t clean=0x10a2d0,invalidate=0x10a310,cleanRange=0x10a270,invalidateRange=0x10a354;
constexpr uint32_t sgir=0xf8f01f00,pending=0xf8f01200,active=0xf8f01300,self15=0x0200000f;
constexpr uint32_t gate=0x19b960,wake=0x1e2224;
constexpr uint32_t probeWords[]={0xe3021026,0xe34a1faf,0xe5801000,0xe12fff1e};
constexpr uint32_t thunkWords[]={0xe92d4010,0xe1a04000,0xe8940007,0xe12fff32,0xe3a00001,0xe584000c,0xe8bd8010};
template<class T,size_t N> constexpr size_t count(const T (&)[N]) {return N;}
template<class T,size_t N> bool hasAddress(const T (&table)[N],uint32_t address) {
    size_t lo=0,hi=N;
    while(lo<hi) {size_t mid=lo+(hi-lo)/2;if(table[mid].address<address)lo=mid+1;else hi=mid;}
    return lo<N && table[lo].address==address;
}
bool contains(uint32_t a,uint32_t start,size_t n) {return !(a&3) && a>=start && uint64_t(a)<uint64_t(start)+n;}
bool branch(uint32_t a,uint32_t target,uint32_t opcode,uint32_t *out) {
    const int64_t delta=int64_t(target)-a-8;
    if(!out || target&3 || delta%4 || delta<-(1<<25) || delta>=(1<<25))return false;
    *out=(opcode&0xff000000u)|(uint32_t(delta/4)&0xffffffu);return true;
}
enum Phase { New,Preflight,Cache,Allocate,WaitAllocation,RemoveWake,PrepareBatch,Body,ProbeBody,Hooks,Verify,Release,Cleanup,FlashPreflight,FlashBody,FlashHooks,FlashVerify,Arm,RetireBatch,Done };
class Loader {
    HblBootIO &io;
    HblBootBatchIO *batch;
    bool afOnly;
    Phase phase=New;
    bool failed=false,cacheReady=false,owned=false,flashLoaded=false,adapterInstalled=false;
    uint32_t adapter[count(hbl_batch_image)]={};
    uint32_t heap=0,raw=0,block=0,body[count(hbl_af_words)]={},bootstrap[count(hbl_bootstrap_words)]={};
    const char *label="new";
    bool fail() {failed=true;return false;}
    bool step(Phase p,const char *text) {
        if(failed)return false;
        phase=p;label=text;
        if(!io.checkpoint(label,0,0,false))return fail();
        return true;
    }
    uint32_t afHook(const HblBootHook &h) const {
        uint32_t target=h.address+8+uint32_t(int32_t((h.replacement&0xffffffu)<<8)>>6);
        uint32_t result=0;
        if(!branch(h.address,target+heap-hbl_af_template_base,h.replacement,&result))return 0;
        return result;
    }
    uint32_t adapterBase() const {return heap+hbl_batch_heap_offset;}
    uint32_t adapterContext() const {return adapterBase()+hbl_batch_adapter_offset;}
    bool wantsAdapter() const {return batch && batch->needsAdapter();}
    bool batchEntry(uint32_t a) const {
        for(const auto &row:hbl_batch_entry_expected)if(a==row[0])return true;
        return false;
    }
    uint32_t originalEntry(uint32_t a) const {
        for(const auto &row:hbl_batch_entry_expected)if(a==row[0])return row[1];
        return 0;
    }
    uint32_t adapterBranch(uint32_t a) const {
        uint32_t result=0;
        if(a!=0x23acac && a!=wake)return 0;
        uint32_t offset=a==wake?hbl_batch_read_dispatch_offset:hbl_batch_decode_offset;
        return branch(a,adapterBase()+offset,0xeb000000,&result)?result:0;
    }
    bool readAllowed(uint32_t a) const {
        if(a&3 || a==sgir)return false;
        if(wantsAdapter() && (batchEntry(a) || (owned && contains(a,adapterBase(),sizeof(adapter)))))return true;
        if(hasAddress(hbl_boot_expected,a) || hasAddress(hbl_boot_guards,a) ||
           hasAddress(hbl_flash_expected,a) || hasAddress(hbl_flash_guards,a))return true;
        if(contains(a,scratch,64) || contains(a,hbl_bootstrap_base,sizeof(bootstrap)))return true;
        if(owned && (a==raw-8 || a==raw-4 || contains(a,heap,sizeof(body))))return true;
        if(raw && (a==raw-8 || a==raw-4))return true;
        return a==0x6bcb7c || contains(a,0x2adc20,36);
    }
    bool rangeAllowed(uint32_t start,uint32_t size) const {
        if(wantsAdapter() && owned && ((start==adapterBase() && size==sizeof(adapter)) ||
           (size==32 && (start==(0x23acacu&~31u) || start==(wake&~31u)))))return true;
        if(start==hbl_bootstrap_base && size==sizeof(bootstrap))return true;
        if(owned && start==heap && size==sizeof(body))return true;
        if(phase>=FlashBody && start==hbl_flash_base && size==sizeof(hbl_flash_words))return true;
        if(size!=32)return false;
        for(const auto &h:hbl_bootstrap_hooks)if(start==(h.address&~31u))return true;
        for(const auto &h:hbl_af_hooks)if(start==(h.address&~31u))return true;
        if(phase>=FlashBody)for(const auto &h:hbl_flash_hooks)if(start==(h.address&~31u))return true;
        return false;
    }
    bool writeAllowed(uint32_t a,uint32_t v) const {
        if(a&3 || phase<Cache || phase==Done || phase==Preflight || phase==FlashPreflight)return false;
        if(wantsAdapter() && owned) {
            if(phase==PrepareBatch && contains(a,adapterBase(),sizeof(adapter)))return v==adapter[(a-adapterBase())/4];
            if((phase==PrepareBatch || phase==RetireBatch) && (a==0x23acac || a==wake))
                return v==(phase==PrepareBatch?adapterBranch(a):originalEntry(a));
            if(adapterInstalled && phase==FlashBody && a==adapterContext()+8)return v==2;
        }
        if(a==sgir)return v==self15;
        if(a==cb)return v==origCB || v==noop || v==clean || v==invalidate || v==scratch ||
            (phase==ProbeBody && owned && v==heap+hbl_offset_af_install_probe);
        if(a==arg)return v==origARG || v==scratch || v==desc ||
            (phase==ProbeBody && owned && v==heap+hbl_offset_af_install_ack);
        if(contains(a,scratch,64)) {
            if(!v)return true;
            if(a<scratch+sizeof(probeWords) && v==probeWords[(a-scratch)/4])return true;
            if(a<scratch+sizeof(thunkWords) && v==thunkWords[(a-scratch)/4])return true;
            if(a==desc) {
                if(rangeAllowed(v,32) || rangeAllowed(v,sizeof(bootstrap)) || rangeAllowed(v,sizeof(body)) || rangeAllowed(v,sizeof(hbl_flash_words)) || (wantsAdapter() && rangeAllowed(v,sizeof(adapter))))return true;
            }
            if(a==desc+4)return v==32 || v==sizeof(bootstrap) || v==sizeof(body) || v==sizeof(hbl_flash_words) || (wantsAdapter() && v==sizeof(adapter));
            if(a==desc+8)return v==cleanRange || v==invalidateRange;
            return false;
        }
        if(phase==Allocate && contains(a,hbl_bootstrap_base,sizeof(bootstrap)))return v==bootstrap[(a-hbl_bootstrap_base)/4];
        if(phase==Release && a==hbl_boot_control)return v==2;
        for(const auto &h:hbl_bootstrap_hooks)if(a==h.address) {
            if(phase==Allocate)return v==h.replacement;
            if(phase==RemoveWake && a==wake)return v==h.original;
            if(phase==Release && a==gate)return v==h.original;
            return false;
        }
        if(phase==Body && owned && contains(a,heap,sizeof(body)))return v==body[(a-heap)/4];
        if(phase==Hooks && owned)for(const auto &h:hbl_af_hooks)if(a==h.address)return v==afHook(h);
        if(phase==FlashBody && contains(a,hbl_flash_base,sizeof(hbl_flash_words)))return v==hbl_flash_words[(a-hbl_flash_base)/4];
        if(phase==FlashHooks)for(const auto &h:hbl_flash_hooks)if(a==h.address)return v==h.replacement;
        return phase==Arm && flashLoaded && a==hbl_flash_record+4 && v==1;
    }
    bool read(uint32_t a,uint32_t *v) {
        if(failed || !readAllowed(a) || !io.read(a,v))return fail();
        return true;
    }
    bool eq(uint32_t a,uint32_t expected,uint32_t mask=~0u) {
        uint32_t v=0;return read(a,&v) && ((v&mask)==expected || fail());
    }
    bool compare(const HblBootCompare *items,size_t n) {
        if(failed || !items || !n || n>20)return fail();
        for(size_t i=0;i<n;++i)if(!readAllowed(items[i].address))return fail();
        if(batch && batch->batchesReady()) return batch->compareBatch(items,n) || fail();
        for(size_t i=0;i<n;++i)if(!eq(items[i].address,items[i].value,items[i].mask))return false;
        return true;
    }
    template<class T,size_t N> bool expected(const T (&table)[N]) {
        HblBootCompare items[20];
        for(size_t i=0;i<N;) {
            size_t n=0;
            while(i<N && n<20) {items[n++]={table[i].address,table[i].value,~0u};++i;}
            if(!compare(items,n))return false;
        }
        return true;
    }
    // 独立AF不写闪光区。全量AF前检已覆盖相同的只读原厂值时不重复通信。
    bool afFactoryFlashCoverage() {
        for(const auto &row:hbl_flash_expected) {
            bool covered=false;
            for(const auto &known:hbl_boot_expected)if(known.address==row.address) {
                if(known.value!=row.value)return fail();covered=true;break;
            }
            if(!covered && !eq(row.address,row.value))return false;
        }
        for(uint32_t a=hbl_flash_base;a<hbl_flash_base+sizeof(hbl_flash_words);a+=4) {
            bool covered=false;
            for(const auto &known:hbl_boot_expected)if(known.address==a) {
                if(known.value)return fail();covered=true;break;
            }
            if(!covered && !eq(a,0))return false;
        }
        return true;
    }
    bool zeros(uint32_t start,size_t words) {
        HblBootCompare items[20];
        for(size_t i=0;i<words;) {
            size_t n=0;
            while(i<words && n<20) {items[n++]={start+uint32_t(i*4),0,~0u};++i;}
            if(!compare(items,n))return false;
        }
        return true;
    }
    bool write(uint32_t a,uint32_t v) {
        if(failed || !writeAllowed(a,v))return fail();
        if(!io.checkpoint(label,a,v,true) || !io.write(a,v))return fail();
        if(a!=sgir && !eq(a,v))return false;
        if(a!=sgir && !io.checkpoint(label,a,v,false))return fail();
        return true;
    }
    bool quietSGI(uint32_t ack=0,uint32_t expected=0) {
        for(unsigned i=0;i<64 && !failed;++i) {
            uint32_t p=0,a=0,v=expected;
            if(!read(pending,&p) || !read(active,&a) || (ack && !read(ack,&v)))return false;
            if(!(p&0x8000) && !(a&0x8000) && v==expected) {
                if(!read(pending,&p) || !read(active,&a))return false;
                if(!((p|a)&0x8000))return true;
            }
            if(!io.pause(1))return fail();
        }
        return fail();
    }
    bool quiet() {return quietSGI() && write(cb,noop) && quietSGI();}
    bool invoke(uint32_t fn,uint32_t parameter,uint32_t ack=0,uint32_t value=0) {
        return quiet() && write(arg,parameter) && write(cb,fn) && write(sgir,self15) && quietSGI(ack,value) &&
            (io.checkpoint(label,sgir,self15,false) || fail()) && quiet();
    }
    bool upload(uint32_t base,const uint32_t *words,size_t n) {
        if(batch && batch->batchesReady() && (phase==Allocate || phase==Body || phase==FlashBody) && base!=scratch) {
            // 先验证整个输入；不把钩子、SGI、缓存描述符或启用动作批量化。
            if(!words || !n || uint64_t(base)+uint64_t(n)*4>0x100000000ull)return fail();
            for(size_t i=0;i<n;++i)if(!writeAllowed(base+uint32_t(i*4),words[i]))return fail();
            for(size_t i=0;i<n;) {
                const size_t take=n-i<60?n-i:60;
                const uint32_t address=base+uint32_t(i*4);
                // 记录整个不确定范围；失败保留 inFlight，不自动重复装载。
                if(!io.checkpoint(label,address,uint32_t(take*4),true) ||
                   !batch->uploadBatch(address,words+i,take) ||
                   !io.checkpoint(label,address,uint32_t(take*4),false))return fail();
                i+=take;
            }
            return true;
        }
        for(size_t i=0;i<n;++i)if(!write(base+uint32_t(i*4),words[i]))return false;
        return true;
    }
    bool prepareAdapter() {
        if(!wantsAdapter())return true;
        if(!owned || !batch->batchSession() || sizeof(adapter)+hbl_batch_heap_offset>32768 ||
           sizeof(body)>hbl_batch_heap_offset || !step(PrepareBatch,"prepare-batch-adapter"))return fail();
        std::memcpy(adapter,hbl_batch_image,sizeof(adapter));
        const uint32_t delta=adapterBase()-hbl_batch_link_base;
        for(uint32_t off:hbl_batch_abs_fixups)adapter[off/4]+=delta;
        for(const auto &pair:hbl_batch_mov_fixups) {
            uint32_t &lo=adapter[pair[0]/4],&hi=adapter[pair[1]/4];
            uint32_t value=(lo&4095)|((lo>>4)&61440)|(((hi&4095)|((hi>>4)&61440))<<16);
            value+=delta;
            lo=(lo&~0x000f0fffu)|((value&61440)<<4)|(value&4095);
            value>>=16;hi=(hi&~0x000f0fffu)|((value&61440)<<4)|(value&4095);
        }
        const unsigned ctx=hbl_batch_adapter_offset/4;
        adapter[ctx]=1;adapter[ctx+1]=heap;adapter[ctx+2]=1;
        adapter[ctx+4]=adapterContext()+16;adapter[ctx+6]=batch->batchSession();
        if(!upload(adapterBase(),adapter,count(adapter)) || !sync(adapterBase(),sizeof(adapter)))return false;
        // 先发布诊断消费者，再发布解码收件入口。
        for(uint32_t a:{wake,0x23acacu})if(!eq(a,originalEntry(a)) || !write(a,adapterBranch(a)) || !sync(a&~31u,32) || !park())return false;
        if(!eq(adapterContext(),1) || !eq(adapterContext()+24,batch->batchSession()) || !eq(adapterContext()+12,0))return false;
        if(!batch->activateBatches(true))return fail();
        adapterInstalled=true;return true;
    }
    bool selectFlashBatch() {
        return !adapterInstalled || write(adapterContext()+8,2);
    }
    bool retireAdapter() {
        if(!adapterInstalled)return true;
        if(!batch->activateBatches(false) || !step(RetireBatch,"retire-batch-adapter") ||
           !eq(adapterContext()+12,0) || !eq(adapterContext()+32,0) || !probe())return fail();
        // 先停止收件，再恢复诊断入口；已归属堆尾中的惰性代码不再可达。
        for(uint32_t a:{0x23acacu,wake})if(!eq(a,adapterBranch(a)) || !write(a,originalEntry(a)) || !sync(a&~31u,32) || !park())return false;
        adapterInstalled=false;return cleanup();
    }
    bool probe() {
        if(!quiet() || !upload(scratch,probeWords,count(probeWords)) || !write(desc,0) ||
           !invoke(clean,scratch) || !invoke(invalidate,scratch) || !invoke(scratch,desc,desc,0xafaf2026))return false;
        if(!upload(scratch,thunkWords,count(thunkWords)) || !invoke(clean,scratch) || !invoke(invalidate,scratch))return false;
        cacheReady=true;return true;
    }
    bool sync(uint32_t start,uint32_t size) {
        if(!cacheReady || !rangeAllowed(start,size))return fail();
        for(uint32_t fn:{cleanRange,invalidateRange}) {
            if(!quiet() || !write(desc,start) || !write(desc+4,size) || !write(desc+8,fn) || !write(desc+12,0) ||
               !invoke(scratch,desc,desc+12,1))return false;
        }
        return true;
    }
    bool park() {return quiet() && write(arg,origARG) && write(cb,origCB) && quietSGI() && eq(cb,origCB) && eq(arg,origARG);}
    bool cleanup() {
        if(!quiet())return false;
        for(uint32_t a=scratch;a<scratch+64;a+=4)if(!write(a,0))return false;
        if(!invoke(clean,scratch) || !invoke(invalidate,scratch) || !park())return false;
        for(uint32_t a=scratch;a<scratch+64;a+=4)if(!eq(a,0))return false;
        cacheReady=false;return true;
    }
    bool idle() {return eq(0x6bb46c,0,255) && eq(0x6bb598,0,255) && eq(0x2adc78,18<<8,0xff00) && eq(0x2adc8c,0,255);}
    bool afVerify() {
        const uint32_t identity=heap+hbl_offset_af_identity;
        HblBootCompare items[20];size_t used=0;
        for(size_t i=0;i<count(body);++i) {
            uint32_t a=heap+uint32_t(i*4);
            if(a>=identity && a<identity+44)continue;
            items[used++]={a,a==heap+hbl_offset_af_install_ack?0x314b4341:body[i],~0u};
            if(used==20) {if(!compare(items,used))return false;used=0;}
        }
        if(used && !compare(items,used))return false;
        for(const auto &h:hbl_af_hooks)if(!eq(h.address,afHook(h)))return false;
        uint32_t sequence=0,key=0;
        if(!read(identity,&sequence) || !read(identity+4,&key))return false;
        if(!sequence) {
            if(key)return fail();
            for(unsigned i=8;i<44;i+=4)if(!eq(identity+i,0))return false;
        } else {
            if(sequence&1)return fail();
            const uint32_t keys[]={0x13131,0x13e3e,0x32727,0x14949,0x12323,0x24f4f,0x1532f,0x12f1c};
            const uint32_t speeds[]={5900,6200,4500,5000,2500,4500,6000,6000};
            uint32_t speed=0;
            for(unsigned i=0;i<8;++i)if(key==keys[i])speed=speeds[i];
            if(!speed)return fail();
            uint32_t focal=0;
            if(!read(0x6bcb7c,&focal))return false;
            const uint32_t off=(focal>>8)&255;
            if((((focal>>16)-off)&255)!=(key&255) || (((focal>>24)-off)&255)!=((key>>8)&255))return fail();
            for(unsigned i=0;i<9;++i) {
                uint32_t cached=0;
                if(!read(identity+8+i*4,&cached) || !eq(0x2adc20+i*4,cached))return false;
                if(i==((focal&255)?4u:3u) && cached!=speed)return fail();
            }
            if(!eq(identity,sequence))return false;
        }
        return idle();
    }
    bool flashVerify(uint32_t armed) {
        for(const auto &h:hbl_flash_hooks)if(!eq(h.address,h.replacement))return false;
        HblBootCompare items[20];size_t used=0;
        for(uint32_t a=hbl_flash_base;a<hbl_flash_record;a+=4) {
            items[used++]={a,hbl_flash_words[(a-hbl_flash_base)/4],~0u};
            if(used==20) {if(!compare(items,used))return false;used=0;}
        }
        if(used && !compare(items,used))return false;
        return eq(hbl_flash_record,0x31534648) && eq(hbl_flash_record+4,armed) && eq(hbl_flash_record+8,0) && idle();
    }
public:
    explicit Loader(HblBootIO &value,HblBootBatchIO *bulk=nullptr,bool onlyAF=false):io(value),batch(bulk),afOnly(onlyAF) {std::memcpy(bootstrap,hbl_bootstrap_words,sizeof(bootstrap));}
    bool run() {
        if(!step(Preflight,"factory-preflight") || !io.version())return fail();
        if(wantsAdapter())for(const auto &row:hbl_batch_entry_expected)if(!eq(row[0],row[1]))return false;
        for(const auto &g:hbl_boot_guards)if(!eq(g.address,g.value,g.mask))return false;
        if(!expected(hbl_boot_expected))return false;
        for(uint32_t a=scratch;a<scratch+64;a+=4)if(!eq(a,0))return false;
        // 旧未完成记录只能在 AF、闪光全部原厂写入区都通过只读检查后继续。
        for(const auto &g:hbl_flash_guards)if(!eq(g.address,g.value,g.mask))return false;
        if(afOnly) {if(!afFactoryFlashCoverage())return false;}
        else {
            if(!expected(hbl_flash_expected))return false;
            if(!zeros(hbl_flash_base,count(hbl_flash_words)))return false;
        }
        if(!idle() || !step(Preflight,"factory-verified"))return false;
        if(!idle() || !step(Cache,"cache-probe") || !probe() || !park() || !idle() || !step(Allocate,"native-allocation"))return false;
        if(!upload(hbl_bootstrap_base,bootstrap,count(bootstrap)) || !sync(hbl_bootstrap_base,sizeof(bootstrap)))return false;
        for(uint32_t a:{gate,wake})for(const auto &h:hbl_bootstrap_hooks)if(h.address==a) {
            if(!eq(a,h.original) || !write(a,h.replacement) || !sync(a&~31u,32))return false;
        }
        if(!step(WaitAllocation,"wait-native-allocation"))return false;
        bool ready=false;
        for(unsigned i=0;i<200 && !failed;++i) {
            uint32_t n=0,s=0;
            if(!read(hbl_boot_control+4,&n) || !read(hbl_boot_control+8,&s))return false;
            if(n && s==1){ready=true;break;}
            if(!io.pause(10))return fail();
        }
        if(!ready || !idle() || !eq(hbl_boot_control,0))return fail();
        uint32_t response[13]={};
        for(unsigned i=0;i<13;++i)if(!read(hbl_boot_request+i*4,&response[i]))return false;
        for(unsigned i=0;i<6;++i)if(response[i]!=bootstrap[(hbl_boot_request-hbl_bootstrap_base)/4+i])return fail();
        raw=response[8];heap=response[9];block=response[10];
        if(response[6]!=3 || response[7] || raw%8 || raw<0x2bacb0 || raw>=0x6baca0 || heap!=((raw+31)&~31u) ||
           block%8 || block<32808 || uint64_t(raw)-8+block>0x6baca0 || uint64_t(heap)+32768>uint64_t(raw)-8+block ||
           response[11]<response[12] || response[11]-response[12]!=block || response[12]<131072)return fail();
        if(!eq(raw-8,0) || !eq(raw-4,block|0x80000000u))return false;
        if(!io.checkpoint("allocation-owned",raw,heap,false) || !io.checkpoint("allocation-block",block,32768,false))return fail();
        owned=true;
        if(!hbl_relocate_af(heap,body,count(body)) || !step(RemoveWake,"restore-wake-entry"))return fail();
        for(const auto &h:hbl_bootstrap_hooks)if(h.address==wake && (!write(wake,h.original) || !sync(wake&~31u,32)))return false;
        for(const auto &h:hbl_bootstrap_hooks)if(h.address==gate && !eq(gate,h.replacement))return false;
        if(!park() || !idle() || !eq(raw-8,0) || !eq(raw-4,block|0x80000000u) || !eq(hbl_boot_control,0) || !prepareAdapter() || !step(Body,"upload-af-owned-body") ||
           !upload(heap,body,count(body)) || !sync(heap,sizeof(body)) || !step(ProbeBody,"execute-af-proof") ||
           !invoke(heap+hbl_offset_af_install_probe,heap+hbl_offset_af_install_ack,heap+hbl_offset_af_install_ack,0x314b4341) || !park())return false;
        if(!step(Hooks,"install-af-hooks"))return false;
        for(const auto &h:hbl_af_hooks)if(!idle() || !eq(h.address,h.original) || !write(h.address,afHook(h)) || !sync(h.address&~31u,32) || !park())return false;
        if(!step(Verify,"verify-af") || !afVerify() || !step(Release,"release-af-gate") || !write(hbl_boot_control,2))return false;
        for(const auto &h:hbl_bootstrap_hooks)if(h.address==gate && (!write(gate,h.original) || !sync(gate&~31u,32)))return false;
        if(!step(Cleanup,"cleanup-af-cache") || !cleanup())return false;
        if(afOnly)return retireAdapter() && step(Done,"af-ready");
        if(!step(FlashPreflight,"flash-preflight"))return false;
        for(const auto &g:hbl_flash_guards)if(!eq(g.address,g.value,g.mask))return false;
        if(!expected(hbl_flash_expected))return false;
        if(!zeros(hbl_flash_base,count(hbl_flash_words)))return false;
        if(!idle() || !step(FlashBody,"upload-flash-body") || !selectFlashBatch() || !probe() ||
           !upload(hbl_flash_base,hbl_flash_words,count(hbl_flash_words)) || !sync(hbl_flash_base,sizeof(hbl_flash_words)) || !step(FlashHooks,"install-flash-hooks"))return false;
        for(const auto &h:hbl_flash_hooks)if(!idle() || !eq(h.address,h.original) || !write(h.address,h.replacement) || !sync(h.address&~31u,32))return false;
        if(!step(FlashVerify,"verify-flash") || !cleanup() || !flashVerify(0) || !afVerify())return false;
        flashLoaded=true;
        return step(Arm,"arm-for-user-exposures") && write(hbl_flash_record+4,1) && flashVerify(1) && retireAdapter() && step(Done,"modules-ready");
    }
};
}

bool hbl_relocate_af(uint32_t base,uint32_t *out,size_t n) {
    if(!out || n!=count(hbl_af_words) || base%32 || base<0x2bacb0 || base>0x6baca0-32768)return false;
    std::memcpy(out,hbl_af_words,sizeof(hbl_af_words));
    auto *bytes=reinterpret_cast<unsigned char *>(out);
    for(const auto &r:hbl_af_relocations) {
        if(r[0]+4>sizeof(hbl_af_words) || r[2]>=sizeof(hbl_af_words))return false;
        if(r[1]==2) {
            uint32_t value=base+r[2];std::memcpy(bytes+r[0],&value,4);
        } else if(r[1]==47 || r[1]==48) {
            uint16_t hi=0,lo=0;std::memcpy(&hi,bytes+r[0],2);std::memcpy(&lo,bytes+r[0]+2,2);
            if((hi&0xfbf0)!=(r[1]==47?0xf240:0xf2c0))return false;
            uint32_t value=((base+r[2])>>(r[1]==48?16:0))&65535;
            hi=uint16_t((hi&~0x40f)|(value>>12)|((value&0x800)>>1));
            lo=uint16_t((lo&~0x70ff)|((value&0x700)<<4)|(value&255));
            std::memcpy(bytes+r[0],&hi,2);std::memcpy(bytes+r[0]+2,&lo,2);
        } else return false;
    }
    return true;
}
bool hbl_load_boot_modules(HblBootIO &io) {
    Loader loader(io);return loader.run();
}

bool hbl_load_boot_modules_batch(HblBootBatchIO &io) {
    Loader loader(io,&io);return loader.run();
}

bool hbl_load_boot_af_batch(HblBootBatchIO &io) {
    Loader loader(io,&io,true);return loader.run();
}
