#ifdef NDEBUG
#undef NDEBUG
#endif
#include "../native/godox_batch_wave.h"
#include <cassert>
#include <cstdio>
#include <vector>
struct Sink {
    std::vector<uint32_t> samples;
    unsigned limit=HBL_POWER_TOTAL_SAMPLES*16;
    bool put(uint32_t sample) {if(samples.size()==limit)return false;samples.push_back(sample);return true;}
};
int main() {
    unsigned active[16]={},values[16]={};uint32_t lut[1024];
    FILE *file=std::fopen("x1d/wireless-flash/build/formal-flash-candidate/reference-lut.bin","rb");
    assert(file);assert(std::fread(lut,sizeof(lut),1,file)==1);assert(std::fgetc(file)==EOF);std::fclose(file);
    for(unsigned i=0;i<16;++i){active[i]=i%2;values[i]=i*5;}
    unsigned checks=0;
    for(unsigned mask: {0u,1u,2u,5u,31u,65535u}) {
        HblPowerBatch b;assert(hbl_power_batch_prepare(&b,mask,active,values,5,5));
        Sink sink;assert(hbl_power_batch_render(b,lut,sink));assert(sink.samples.size()==b.samples);
        unsigned g=0;
        for(unsigned i=0;i<16;++i)if(mask&(1u<<i)) {
            unsigned index;assert(hbl_formal_power_index(&index,i,active[i],values[i]));assert(b.index[g]==index);
            uint32_t expected;assert(hbl_formal_wave_hash(&expected,index,5,5,lut));
            uint32_t actual=0x811c9dc5u;
            for(unsigned j=0;j<HBL_POWER_TOTAL_SAMPLES;++j)actual=(actual^sink.samples[g*HBL_POWER_TOTAL_SAMPLES+j])*0x01000193u;
            assert(actual==expected);++g;++checks;
        }
        assert(g==b.count);
        if(b.samples){Sink shortSink;shortSink.limit=b.samples-1;assert(!hbl_power_batch_render(b,lut,shortSink));}
    }
    HblPowerBatch b;assert(!hbl_power_batch_prepare(&b,65536,active,values,5,5));
    assert(!hbl_power_batch_prepare(&b,1,active,values,0,5));
    values[0]=81;assert(!hbl_power_batch_prepare(&b,1,active,values,5,5));
    assert(hbl_power_batch_prepare(&b,2,active,values,5,5));
    std::printf("batch-wave independent frame hashes=%u; full-list samples=%u; hardware-requests=0\n",checks,HBL_POWER_TOTAL_SAMPLES*16);
}
