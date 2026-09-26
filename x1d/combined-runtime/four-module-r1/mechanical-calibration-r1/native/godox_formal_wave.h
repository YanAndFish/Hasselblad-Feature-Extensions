#ifndef HBL_GODOX_FORMAL_WAVE_H
#define HBL_GODOX_FORMAL_WAVE_H
#include "godox_power_wave.h"

/* CH 表绑定 AD400Pro V1.50；ID 与 A-F/0-9 地址绑定 X3Pro C V1.22。
 * 频道载波使用参考表完整频率字，复用已验证波形的调制参数。
 * 灯型能否选择某一组仍取决于接收端；不宣称全部灯都支持十六组。
 */
enum { HBL_FORMAL_GROUPS=16, HBL_FORMAL_VALUES=82,
       HBL_FORMAL_POWER_WAVES=HBL_FORMAL_GROUPS*HBL_FORMAL_VALUES,
       HBL_FORMAL_LAMP_BASE=HBL_FORMAL_POWER_WAVES,
       HBL_FORMAL_CONTROL_WAVES=HBL_FORMAL_POWER_WAVES+HBL_FORMAL_GROUPS*2,
       HBL_FORMAL_FIRE_INDEX=HBL_FORMAL_CONTROL_WAVES,
       HBL_FORMAL_WAVES=HBL_FORMAL_CONTROL_WAVES+1,
       HBL_FORMAL_CONFIG_BASE=8192, HBL_FORMAL_CONFIG_COUNT=3200,
       HBL_FORMAL_GROUP_MASK=65535 };

static inline int hbl_formal_config_valid(unsigned channel,unsigned id) {
    return channel>=1 && channel<=32 && id<=99; /* ID 0 = OFF */
}
static inline unsigned hbl_formal_frequency_quarters(unsigned channel) {
    static const uint8_t offsets[32]={4,10,16,24,30,36,44,50,59,64,70,79,84,90,97,104,
                                    110,119,124,130,139,144,150,159,164,170,179,184,190,199,204,210};
    return channel>=1 && channel<=32 ? offsets[channel-1] : 0;
}
static inline unsigned hbl_formal_chanspec(unsigned channel) {
    const unsigned q=hbl_formal_frequency_quarters(channel);
    return q ? 0x1000u+q/20+1 : 0;
}
static inline uint32_t hbl_formal_phase_step(unsigned channel,unsigned bit) {
    /* 原参考寄存器的实际频率保留小数项；CH5 两个值与已出光版本逐位相同。
     * 各 CH 仅平移载波，FSK 间距及逐位采样长度保持原基线。 */
    static const uint32_t one[32]={100625612u,261690163u,422754713u,100664934u,261686886u,422751436u,100661657u,261726208u,503301734u,100658380u,261722931u,503298457u,100655104u,261719654u,449621196u,100651827u,261716377u,503291904u,100648550u,261713100u,503288627u,100645273u,261709824u,503285350u,100641996u,261706547u,503282073u,100638720u,261703270u,503278796u,100635443u,261699993u};
    if(channel<1 || channel>32 || bit>1) return 0;
    return one[channel-1]+(bit ? 0 : 13418496u);
}
static inline unsigned hbl_formal_config_selector(unsigned channel,unsigned id) {
    return hbl_formal_config_valid(channel,id) ? HBL_FORMAL_CONFIG_BASE+(channel-1)*100+id : 0;
}
static inline int hbl_formal_frame_config(uint8_t out[12],unsigned index,unsigned id) {
    if (!out || index>=HBL_FORMAL_WAVES || id>99) return 0;
    unsigned sync=0,remainder=0;
    for (int bit=15;bit>=0;--bit) {
        remainder=(remainder<<1)|((0xc368u>>bit)&1u);
        if (remainder>=id+1) { remainder-=id+1; sync|=1u<<bit; }
    }
    for (unsigned i=0;i<4;++i) out[i]=0xaa;
    out[4]=(uint8_t)(sync>>8); out[5]=(uint8_t)sync;
    out[6]=out[4]; out[7]=out[5]; out[8]=0xa9;
    if (index==HBL_FORMAL_FIRE_INDEX) {
        out[9]=0x50; out[10]=0xb4; out[11]=9;
    } else if (index>=HBL_FORMAL_LAMP_BASE) {
        const unsigned group=(index-HBL_FORMAL_LAMP_BASE)/2;
        out[9]=(uint8_t)(group<6 ? 0x0a+group : group-6);
        out[10]=0xd3; out[11]=(uint8_t)((index-HBL_FORMAL_LAMP_BASE)%2);
    } else {
        const unsigned group=index/HBL_FORMAL_VALUES,value=index%HBL_FORMAL_VALUES;
        out[9]=(uint8_t)(group<6 ? 0x0a+group : group-6);
        out[10]=0xbc; out[11]=(uint8_t)(value==81 ? 255 : value);
    }
    return 1;
}
static inline int hbl_formal_runs_config(HblGodoxPowerRun out[96],unsigned index,unsigned channel,unsigned id) {
    uint8_t frame[12];
    if (!out || !hbl_formal_config_valid(channel,id) || !hbl_formal_frame_config(frame,index,id)) return 0;
    const uint32_t one=hbl_formal_phase_step(channel,1),zero=hbl_formal_phase_step(channel,0);
    for (unsigned i=0;i<96;++i) {
        out[i].samples=(uint16_t)(160+(i==0 || i==25 || i==51 || i==76));
        out[i].reserved=0;
        out[i].phase_step=frame[i/8]&(1u<<(7-i%8)) ? one : zero;
    }
    return 1;
}
static inline int hbl_formal_wave_hash(uint32_t *out_hash,unsigned index,unsigned channel,unsigned id,
                                       const uint32_t lut[1024]) {
    uint8_t frame[12];
    if (!out_hash || !lut || !hbl_formal_config_valid(channel,id) || !hbl_formal_frame_config(frame,index,id)) return 0;
    uint32_t hash=0x811c9dc5u,phase=0;
    const uint32_t one=hbl_formal_phase_step(channel,1),zero=hbl_formal_phase_step(channel,0);
    for (unsigned i=0;i<HBL_POWER_LEADING_ZERO_SAMPLES;++i) hash*=0x01000193u;
    for (unsigned i=0;i<96;++i) {
        const uint32_t step=frame[i/8]&(1u<<(7-i%8)) ? one : zero;
        const unsigned samples=160+(i==0 || i==25 || i==51 || i==76);
        for (unsigned j=0;j<samples;++j) { phase+=step; hash=(hash^lut[phase>>22])*0x01000193u; }
    }
    for (unsigned i=0;i<HBL_POWER_TRAILING_ZERO_SAMPLES;++i) hash*=0x01000193u;
    *out_hash=hash; return hash!=0;
}
static inline int hbl_formal_frame(uint8_t out[12],unsigned index) { return hbl_formal_frame_config(out,index,5); }
static inline int hbl_formal_runs(HblGodoxPowerRun out[96],unsigned index) { return hbl_formal_runs_config(out,index,5,5); }
static inline int hbl_formal_power_index(unsigned *out,unsigned group,unsigned active,unsigned tenthStops) {
    if (!out || group>=HBL_FORMAL_GROUPS || active>1 || tenthStops>80) return 0;
    *out=group*HBL_FORMAL_VALUES+(active ? 80-tenthStops : 81);
    return 1;
}
static inline int hbl_formal_lamp_index(unsigned *out,unsigned group,unsigned on) {
    if (!out || group>=HBL_FORMAL_GROUPS || on>1) return 0;
    *out=HBL_FORMAL_LAMP_BASE+group*2+on; return 1;
}
#endif
