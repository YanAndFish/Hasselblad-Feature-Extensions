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


#include "../build/controller-first/early_data.h"
struct EarlyModel : IntegratedBatchModel {
 bool earlyPermit=false,fullVerified=false,recovery=false,corruptEarly=false;
 EarlyModel(){for(const auto &r:earlyDependencies)mem[r[0]]=r[1];}
 bool earlyBootstrapAllowed() const override{return !recovery;}
 bool checkpoint(const char *text,uint32_t,uint32_t,bool) override {
  if(failed){++afterFailure;return false;}
  stage=text;
  if(corruptEarly && earlyPermit && activeBatch && stage=="factory-preflight")mem[0x2b2880]^=1;
  if(++checkpoints==failCheckpoint){failed=true;return false;}
  if(stage=="early-bootstrap-verified")earlyPermit=true;
  if(stage=="factory-verified")fullVerified=true;
  if(corruptCode && stage=="verify-af")mem[heap]^=1;
  return true;
 }
 bool write(uint32_t a,uint32_t v) override {
  assert(earlyPermit || fullVerified);
  if(!fullVerified) {
   assert(a==0x23acac || a==0x1e2224 || a==0x2a5074 || a==0x2a5078 || a==0xf8f01f00 ||
    (a>=0x2b2800 && a<0x2b2840) || (a>=0x2b2880 && a<0x2b2880+sizeof(earlyImage)));
  }
  factoryVerified=true;
  return Model::write(a,v);
 }
};

struct Profile : EarlyModel {
 unsigned last=0;
 bool checkpoint(const char *text,uint32_t a,uint32_t v,bool pending) override {
  unsigned now=requests-batchedReads-2*batchedWrites+packets;
  if(stage!=text){if(!stage.empty())std::printf("%s %u\n",stage.c_str(),now-last);last=now;}
  return EarlyModel::checkpoint(text,a,v,pending);
 }
};
int main(){Profile m;assert(hbl_load_boot_af_batch(m));return 0;}
