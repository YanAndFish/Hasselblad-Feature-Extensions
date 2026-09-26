// 复用原装载模型，保留独立的串行参考和逐字故障边界。
#define main legacy_model_main
#include "boot_loader.test.cpp"
#undef main
#include "../native/boot_batch_mailbox.h"
struct BatchModel : Model {
    unsigned packets=0,batchedReads=0,batchedWrites=0,operation=0;
    HblBatchMailbox mailbox={0,0x12345678,0,{42,0,0},{}};
    HblBatchState &session=mailbox.state;
    std::vector<HblBootCompare> approved;
    static void put(std::vector<unsigned char> &p,uint32_t v) {
        for(unsigned i=0;i<4;++i)p.push_back(static_cast<unsigned char>(v>>(8*i)));
    }
    static int allow(void *ctx,uint32_t op,uint32_t a,uint32_t v,uint32_t mask) {
        auto *m=static_cast<BatchModel *>(ctx);
        if(op!=m->operation)return 0;
        for(const auto &x:m->approved)if(x.address==a && x.value==v && x.mask==mask)return 1;
        return 0;
    }
    static int get(void *ctx,uint32_t a,uint32_t *v) {
        auto *m=static_cast<BatchModel *>(ctx);if(m->operation==1)++m->batchedReads;
        return m->read(a,v);
    }
    static int set(void *ctx,uint32_t a,uint32_t v) {
        auto *m=static_cast<BatchModel *>(ctx);++m->batchedWrites;return m->write(a,v);
    }
    bool execute(std::vector<unsigned char> &p) {
        ++packets;HblBatchMemory memory={this,allow,get,set};
        std::vector<unsigned char> frame={0xf4,0,5,1};frame.insert(frame.end(),p.begin(),p.end());
        put(frame,hbl_batch_crc(frame.data(),frame.size()));
        const uint32_t seq=session.sequence;
        if(hbl_batch_stage(&mailbox,frame.data(),frame.size())!=8){failed=true;return false;}
        unsigned char reply[9]={};
        assert(hbl_batch_consume(&mailbox,&memory,frame.data(),reply)==1);
        assert(reply[0]==0xf5 && reply[1]==0 && reply[2]==1 && reply[3]==5 && hbl_batch_u32(reply+4)==seq);
        const unsigned completed=requests;
        assert(!hbl_batch_consume(&mailbox,&memory,frame.data(),reply) && requests==completed);
        if(reply[8])failed=true;
        return reply[8]==0;
    }
    std::vector<unsigned char> header(unsigned op,unsigned n,uint32_t base) {
        std::vector<unsigned char> p;operation=op;approved.clear();
        for(uint32_t v:{0x31424248u,42u,session.sequence,op,n,base,0u})put(p,v);
        return p;
    }
    bool compareBatch(const HblBootCompare *items,size_t n) override {
        assert(items && n && n<=20);auto p=header(1,unsigned(n),0);
        for(size_t i=0;i<n;++i) {approved.push_back(items[i]);put(p,items[i].address);put(p,items[i].value);put(p,items[i].mask);}
        assert(p.size()+4<=272);return execute(p);
    }
    bool uploadBatch(uint32_t address,const uint32_t *words,size_t n) override {
        assert(words && n && n<=60);auto p=header(2,unsigned(n),address);
        for(size_t i=0;i<n;++i) {approved.push_back({address+uint32_t(i*4),words[i],~0u});put(p,words[i]);}
        assert(p.size()+4<=272);return execute(p);
    }
};
#include "../build/batch-model/adapter_data.h"
struct IntegratedBatchModel : BatchModel {
    bool activeBatch=false;
    IntegratedBatchModel() {for(const auto &row:hbl_batch_entry_expected)mem[row[0]]=row[1];}
    bool needsAdapter() const override {return true;}
    bool batchesReady() const override {return activeBatch;}
    uint32_t batchSession() const override {return 42;}
    bool activateBatches(bool enable) override {
        if(activeBatch==enable)return false;activeBatch=enable;return true;
    }
};

int main(){IntegratedBatchModel before,m;assert(hbl_load_boot_af_batch(m));assert(m.stage=="af-ready" && !m.activeBatch);
 for(const auto &w:m.writes){assert(!(w.first>=hbl_flash_base && w.first<hbl_flash_base+sizeof(hbl_flash_words)));for(const auto &h:hbl_flash_hooks)assert(w.first!=h.address);}
 for(const auto &h:hbl_flash_hooks)assert(m.mem[h.address]==before.mem[h.address]);
 assert(m.mem[0x1e2224]==before.mem[0x1e2224] && m.mem[0x23acac]==before.mem[0x23acac]);
 unsigned checks=1;
 for(uint32_t a=hbl_flash_base;a<hbl_flash_base+sizeof(hbl_flash_words);a+=4){IntegratedBatchModel bad;bad.mem[a]=1;assert(!hbl_load_boot_af_batch(bad));assert(bad.writes.empty());++checks;}
 for(const auto &row:hbl_flash_expected){IntegratedBatchModel bad;bad.mem[row.address]^=1;assert(!hbl_load_boot_af_batch(bad));assert(bad.writes.empty());++checks;}

 for(unsigned i=1;i<=m.requests;++i){IntegratedBatchModel bad;bad.failRequest=i;assert(!hbl_load_boot_af_batch(bad));assert(bad.requests==i && !bad.afterFailure);++checks;}
 for(unsigned i=1;i<=m.checkpoints;++i){IntegratedBatchModel bad;bad.failCheckpoint=i;assert(!hbl_load_boot_af_batch(bad));assert(bad.checkpoints==i && !bad.afterFailure);++checks;}
 std::printf("af-only-checks=%u calls=%u flash-writes=0 entries-restored=1 hardware=0\n",checks,m.requests-m.batchedReads-2*m.batchedWrites+m.packets);return 0;}
