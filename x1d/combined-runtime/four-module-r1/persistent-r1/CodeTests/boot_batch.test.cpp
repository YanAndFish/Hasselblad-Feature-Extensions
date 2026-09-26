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
int main() {
    Model serial;assert(hbl_load_boot_modules(serial));
    BatchModel normal;assert(hbl_load_boot_modules_batch(normal));
    assert(normal.mem==serial.mem && normal.writes==serial.writes);
    assert(normal.stage=="modules-ready" && normal.requests==serial.requests);
    unsigned checks=1;
    // 帧截断、会话/序号/保留字段异常及末项越权，全部在内存访问前拒绝。
    for(unsigned mode=0;mode<42;++mode) {
        BatchModel m;m.factoryVerified=true;auto p=m.header(2,2,0x2b3000);
        BatchModel::put(p,1);BatchModel::put(p,2);
        m.approved={{0x2b3000,1,~0u},{0x2b3004,2,~0u}};
        if(mode<36)p.resize(mode);
        else if(mode==36)p[4]^=1;
        else if(mode==37)p[8]^=1;
        else if(mode==38)p[24]=1;
        else if(mode==39)p[16]=65;
        else if(mode==40)p[20]=1;
        else m.approved.pop_back();
        assert(!m.execute(p));assert(m.writes.empty() && !m.requests);
        const unsigned calls=m.requests;assert(!m.execute(p) && m.requests==calls);++checks;
    }
    {BatchModel m;m.factoryVerified=true;auto p=m.header(2,1,0x2b3000);
     BatchModel::put(p,1);m.approved={{0x2b3000,1,~0u}};
     assert(m.execute(p));unsigned before=m.requests;
     assert(!m.execute(p) && m.requests==before);++checks;}

    for(unsigned i=1;i<=normal.requests;++i) {
        BatchModel m;m.failRequest=i;
        assert(!hbl_load_boot_modules_batch(m));assert(m.requests==i && !m.afterFailure);++checks;
    }
    for(unsigned i=1;i<=normal.checkpoints;++i) {
        BatchModel m;m.failCheckpoint=i;
        assert(!hbl_load_boot_modules_batch(m));assert(m.checkpoints==i && !m.afterFailure);++checks;
    }
    BatchModel corrupt;corrupt.mem[hbl_boot_expected[33].address]^=1;
    assert(!hbl_load_boot_modules_batch(corrupt) && corrupt.writes.empty());++checks;
    BatchModel badHeap;badHeap.badAllocation=true;
    assert(!hbl_load_boot_modules_batch(badHeap));
    for(const auto &w:badHeap.writes)assert(w.first<badHeap.heap || w.first>=badHeap.heap+32768);++checks;
    BatchModel stale;stale.mem=normal.mem;
    assert(!hbl_load_boot_modules_batch(stale) && stale.writes.empty());++checks;
    const unsigned calls=normal.requests-normal.batchedReads-2*normal.batchedWrites+normal.packets;
    std::printf("checks=%u exact-memory-and-write-order=1 serial-calls=%u candidate-calls=%u batches=%u hardware-requests=0\n",checks,normal.requests,calls,normal.packets);
    IntegratedBatchModel integrated;assert(hbl_load_boot_modules_batch(integrated));
    assert(!integrated.activeBatch && integrated.stage=="modules-ready");
    Model reference;for(const auto &row:hbl_batch_entry_expected)reference.mem[row[0]]=row[1];
    assert(hbl_load_boot_modules(reference));
    const uint32_t begin=integrated.heap+hbl_batch_heap_offset,end=begin+sizeof(hbl_batch_image);
    for(const auto &item:integrated.mem)if(item.first<begin || item.first>=end)assert(reference.mem[item.first]==item.second);
    for(const auto &item:reference.mem)assert(integrated.mem[item.first]==item.second);
    unsigned lifecycleChecks=1;
    for(unsigned i=1;i<=integrated.requests;++i) {
        IntegratedBatchModel m;m.failRequest=i;
        assert(!hbl_load_boot_modules_batch(m) && m.requests==i && !m.afterFailure);++lifecycleChecks;
    }
    for(unsigned i=1;i<=integrated.checkpoints;++i) {
        IntegratedBatchModel m;m.failCheckpoint=i;
        assert(!hbl_load_boot_modules_batch(m) && m.checkpoints==i && !m.afterFailure);++lifecycleChecks;
    }
    const unsigned startupCalls=integrated.requests-integrated.batchedReads-2*integrated.batchedWrites+integrated.packets;
    std::printf("lifecycle-checks=%u first-upload-included=1 startup-calls=%u helper-words=%zu original-entries-restored=1\n",lifecycleChecks,startupCalls,sizeof(hbl_batch_image)/4);
    return 0;
}
