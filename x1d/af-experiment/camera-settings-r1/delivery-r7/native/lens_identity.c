#include "af_policy.h"
#define R8(a) (*(volatile unsigned char *)(a))
/* X1D 1.25.0: observers run after the original UNKNOWN / NEW LENS stores.
   No query, factory cache write, or model substitution is performed here. */
struct Identity {volatile u32 sequence,key;volatile unsigned char row[36];};
__attribute__((section(".data.state"),used)) struct Identity af_identity={0};
void af_identity_invalidate(void){
    af_identity.sequence++;__asm__ volatile("dmb ish":::"memory");
    af_identity.key=0;__asm__ volatile("dmb ish":::"memory");af_identity.sequence++;
}
void af_identity_publish(u32 lo,u32 hi,u32 version){
    af_identity.sequence++;__asm__ volatile("dmb ish":::"memory");af_identity.key=0;
    if(R8(0x2adc79)==18 && lo && hi && lo<255 && hi<255 && version<255){
        for(u32 i=0;i<36;i++)af_identity.row[i]=R8(0x2ad998+18*36+i);
        if(af_identity.row[5]==lo && af_identity.row[6]==hi)
            af_identity.key=lo|(hi<<8)|(version<<16);
    }
    __asm__ volatile("dmb ish":::"memory");af_identity.sequence++;
}
/* A token is usable only for this exact successful parameter publication. */
u32 af_identity_token(u32 *key){
    u32 sequence=af_identity.sequence,k=af_identity.key;
    __asm__ volatile("dmb ish":::"memory");
    if(!sequence || (sequence&1) || !k || R8(0x2adc79)!=18)return 0;
    u32 offset=R8(0x6bcb7d);
    if(((R8(0x6bcb7e)-offset)&255)!=(k&255) ||
       ((R8(0x6bcb7f)-offset)&255)!=((k>>8)&255))return 0;
    for(u32 i=0;i<36;i++)if(af_identity.row[i]!=R8(0x2ad998+18*36+i))return 0;
    __asm__ volatile("dmb ish":::"memory");
    if(af_identity.sequence!=sequence || R8(0x2adc79)!=18)return 0;
    if(key)*key=k;return sequence;
}
