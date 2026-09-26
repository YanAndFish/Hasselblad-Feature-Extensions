#ifndef HBL_GODOX_BATCH_WAVE_H
#define HBL_GODOX_BATCH_WAVE_H
#include "godox_formal_wave.h"

/* 单个逻辑波形：按 UI 列表顺序包含所有参数帧（包括 OFF）。
 * 保留已验证单帧的前后静默及调制采样，不擅自缩短协议间隔。
 * 此生成器不访问设备；硬件播放必须另行证明能覆盖 samples 的全长。 */
struct HblPowerBatch {
    uint32_t index[HBL_FORMAL_GROUPS];
    unsigned count,channel,id;
    uint32_t samples;
};
static inline bool hbl_power_batch_prepare(HblPowerBatch *out,unsigned mask,
                                         const unsigned active[16],const unsigned tenths[16],
                                         unsigned channel,unsigned id) {
    if(!out || !active || !tenths || mask>HBL_FORMAL_GROUP_MASK || !hbl_formal_config_valid(channel,id)) return false;
    HblPowerBatch next={};next.channel=channel;next.id=id;
    for(unsigned i=0;i<16;++i) {
        if(!(mask&(1u<<i))) continue;
        if(!hbl_formal_power_index(&next.index[next.count],i,active[i],tenths[i])) return false;
        ++next.count;
    }
    next.samples=next.count*HBL_POWER_TOTAL_SAMPLES;
    *out=next;return true;
}
template<class Sink>
static bool hbl_power_batch_render(const HblPowerBatch &batch,const uint32_t lut[1024],Sink &sink) {
    if(!lut || batch.count>16 || batch.samples!=batch.count*HBL_POWER_TOTAL_SAMPLES ||
       !hbl_formal_config_valid(batch.channel,batch.id)) return false;
    for(unsigned group=0;group<batch.count;++group) {
        uint8_t frame[12];
        if(batch.index[group]>=HBL_FORMAL_POWER_WAVES ||
           !hbl_formal_frame_config(frame,batch.index[group],batch.id)) return false;
        uint32_t phase=0;
        for(unsigned i=0;i<HBL_POWER_LEADING_ZERO_SAMPLES;++i) if(!sink.put(0)) return false;
        for(unsigned i=0;i<96;++i) {
            const uint32_t step=hbl_formal_phase_step(batch.channel,(frame[i/8]>>(7-i%8))&1);
            for(unsigned j=0;j<160u+unsigned(i==0 || i==25 || i==51 || i==76);++j) {
                phase+=step;if(!sink.put(lut[phase>>22])) return false;
            }
        }
        for(unsigned i=0;i<HBL_POWER_TRAILING_ZERO_SAMPLES;++i) if(!sink.put(0)) return false;
    }
    return true;
}
#endif
