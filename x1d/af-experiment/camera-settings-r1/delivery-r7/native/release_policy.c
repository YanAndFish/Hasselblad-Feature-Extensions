#include "af_policy.h"
struct Lens {u32 key,speed,maximum;};
/* Reference firmware identity triplets packed as lo | hi<<8 | version<<16.
   Scope is the eight requested lenses without an extender. */
static const struct Lens lenses[]={
    {49u|(49u<<8)|(1u<<16),5900,23600}, /* 38V */
    {62u|(62u<<8)|(1u<<16),6200,24800}, /* 55V */
    {39u|(39u<<8)|(3u<<16),4500,18000}, /* 28P */
    {73u|(73u<<8)|(1u<<16),5000,20000}, /* 75P */
    {35u|(35u<<8)|(1u<<16),2500,10000}, /* 25V */
    {79u|(79u<<8)|(2u<<16),4500,18000}, /* 90V */
    {47u|(83u<<8)|(1u<<16),6000,24000}, /* 35-100E */
    {28u|(47u<<8)|(1u<<16),6000,24000}, /* 20-35E */
};
u32 af_policy_begin(struct AfPolicy *p,u32 generation){
    (void)generation;u32 key=0,token=af_identity_token(&key),reported=token?af_reported_start_speed():0;
    *p=(struct AfPolicy){.start_speed=AP_DYNAMIC_70,.start_samples=10,.far_first=1,.fine_advance_ms=100,
        .identity_token=token,.identity_key=key,.reported_speed=reported};
    for(u32 i=0;i<sizeof(lenses)/sizeof(lenses[0]);i++)if(lenses[i].key==key && lenses[i].speed==reported){
        p->eligible=1;p->probe=lenses[i].maximum;p->fast=lenses[i].maximum;return 0;
    }
    return 1;
}
int af_policy_current(const struct AfPolicy *p){
    u32 key=0,token=af_identity_token(&key);
    return p->eligible && token && token==p->identity_token && key==p->identity_key &&
        af_reported_start_speed()==p->reported_speed;
}
extern void af_identity_publish(u32,u32,u32),af_identity_invalidate(void);
void af_release_seed_current(void){
    volatile unsigned char *model=(volatile unsigned char *)0x2adc79;
    volatile unsigned char *focal=(volatile unsigned char *)0x6bcb7d;
    if(*model!=18)return;
    u32 offset=focal[0],lo=(focal[1]-offset)&255,hi=(focal[2]-offset)&255;
    volatile unsigned char *row=(volatile unsigned char *)(0x2ad998+18*36);
    for(u32 i=0;i<sizeof(lenses)/sizeof(lenses[0]);i++){
        u32 speed=*(volatile u32 *)(row+(focal[-1]?16:12));
        if((lenses[i].key&255)==lo && ((lenses[i].key>>8)&255)==hi &&
           row[5]==lo && row[6]==hi && speed==lenses[i].speed){
            af_identity_publish(lo,hi,(lenses[i].key>>16)&255);return;
        }
    }
}
