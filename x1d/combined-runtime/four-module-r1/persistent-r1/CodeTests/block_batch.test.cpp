// 复用原装载模型，保留独立的串行参考和逐字故障边界。
#define main legacy_model_main
#include "boot_loader.test.cpp"
#undef main
#include "../build/block-write/boot_batch_mailbox.h"
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


#include "../build/block-write/early_data.h"
struct EarlyModel : IntegratedBatchModel {
 bool earlyPermit=false,fullVerified=false,recovery=false,corruptEarly=false;
 EarlyModel(){for(const auto &r:earlyDependencies)mem[r[0]]=r[1];}
 bool version() override {assert(false && "production boot must not query firmware version");return false;}
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
  const uint32_t cb=mem[0x2a5074],arg=mem[0x2a5078];
  const bool pair=a==0xf8f01f00 && cb==0x2b2800 && mem[cb+16]==0xe894000f;
  const uint32_t second=mem[arg+12];
  bool resident=a==0xf8f01f00 && cb==heap+8192;
  if(resident)mem[0x2a5074]=0x10a2d0;
  bool ok=Model::write(a,v);
  if(resident)mem[0x2a5074]=cb;
  if(ok && resident && !noAck) {
   assert(arg==heap+24576 && mem[arg]==0x31494641 && mem[arg+16]==0);
   mem[arg+16]=1;
   for(unsigned off=0;off<sizeof(hbl_af_words);off+=4)mem[heap+off]=mem[heap+4096+off];
   mem[heap+hbl_offset_af_install_ack]=0x314b4341;
   for(const auto &h:hbl_af_hooks) {
    assert(mem[h.address]==h.original);
    mem[h.address]=(h.replacement&0xff000000u)|(((h.replacement&0xffffffu)+((heap-hbl_af_template_base)>>2))&0xffffffu);
   }
   mem[hbl_boot_control]=2;
   for(const auto &h:hbl_bootstrap_hooks)if(h.address==0x19b960)mem[h.address]=h.original;
   mem[arg+20]=0;mem[arg+16]=2;
  }
  if(ok && pair && !noAck){assert(mem[arg+8]==0x10a270 && second==0x10a354);mem[arg+12]=second;mem[arg+16]=1;}
  return ok;
 }
};
int main(){
 EarlyModel m;bool ok=hbl_load_boot_af_batch(m);
 if(!ok){std::fprintf(stderr,"early failed stage=%s read=%08x writes=%zu requests=%u\n",m.stage.c_str(),m.lastRead,m.writes.size(),m.requests);return 1;}
 assert(m.stage=="af-ready" && !m.activeBatch);
 for(const auto &h:hbl_flash_hooks)assert(m.mem[h.address]==h.original);
 for(const auto &r:hbl_batch_entry_expected)assert(m.mem[r[0]]==r[1]);
 unsigned checks=1;
 for(unsigned i=1;i<=m.requests;++i){EarlyModel bad;bad.failRequest=i;assert(!hbl_load_boot_af_batch(bad));assert(bad.requests==i && !bad.afterFailure);++checks;}
 for(unsigned i=1;i<=m.checkpoints;++i){EarlyModel bad;bad.failCheckpoint=i;assert(!hbl_load_boot_af_batch(bad));assert(bad.checkpoints==i && !bad.afterFailure);++checks;}
 for(const auto &g:hbl_boot_guards){EarlyModel bad;bad.mem[g.address]^=g.mask&(~g.mask+1);assert(!hbl_load_boot_af_batch(bad));assert(bad.writes.empty());++checks;}
 EarlyModel badHeap;badHeap.badAllocation=true;assert(!hbl_load_boot_af_batch(badHeap));for(const auto &w:badHeap.writes)assert(w.first<badHeap.heap || w.first>=badHeap.heap+32768);++checks;
 EarlyModel recovery;recovery.recovery=true;assert(!hbl_load_boot_af_batch(recovery) && recovery.writes.empty());++checks;
 std::printf("early checks=%u calls=%u writes=%zu hardware=0\n",checks,m.requests-m.batchedReads-2*m.batchedWrites+m.packets,m.writes.size());
 return 0;
}
