#ifdef NDEBUG
#undef NDEBUG
#endif
#include "../native/godox_formal_wave.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv) {
    assert(argc==2);
    uint32_t lut[1024]; FILE *file=fopen(argv[1],"rb"); assert(file);
    assert(fread(lut,sizeof(lut),1,file)==1); fclose(file);
    for (unsigned i=0;i<HBL_FORMAL_WAVES;++i) {
        uint8_t frame[12]; HblGodoxPowerRun runs[96]; uint32_t hash=0;
        assert(hbl_formal_frame(frame,i) && hbl_formal_runs(runs,i));
        assert(hbl_godox_power_wave_hash(&hash,runs,lut));
        for (unsigned b=0;b<12;++b) printf("%02x",frame[b]);
        printf(" %08x\n",hash);
    }
    unsigned index=999;
    assert(hbl_formal_power_index(&index,3,1,33) && index==3*82+47);
    assert(hbl_formal_power_index(&index,3,0,33) && index==3*82+81);
    assert(!hbl_formal_power_index(&index,HBL_FORMAL_GROUPS,1,0) && index==3*82+81);
    assert(!hbl_formal_power_index(&index,0,2,0) && !hbl_formal_power_index(&index,0,1,81));
    uint8_t frame[12]; memset(frame,0x55,sizeof(frame));
    assert(!hbl_formal_frame(frame,HBL_FORMAL_WAVES));
    for (unsigned i=0;i<12;++i) assert(frame[i]==0x55);
    return 0;
}
