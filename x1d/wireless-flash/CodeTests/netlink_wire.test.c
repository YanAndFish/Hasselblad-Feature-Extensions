#include "../native/rf_netlink_wire.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned passed;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"check failed at %d: %s\n",__LINE__,#x); exit(1); } ++passed; } while (0)
static size_t attr(uint8_t *out,size_t off,uint16_t type,const void *data,size_t n) {
    rf_put16(out+off,(uint16_t)(n+4)); rf_put16(out+off+2,type);
    memcpy(out+off+4,data,n); return off+rf_align4(n+4);
}
static size_t reply(uint8_t *out,unsigned outputLength) {
    uint8_t nested[32]={0},small[8]={0}; size_t inside=0,total=20;
    memset(out,0,128); rf_put16(out+4,35); rf_put32(out+8,7); rf_put32(out+12,9); out[16]=103;
    rf_put16(small,(uint16_t)outputLength); inside=attr(nested,inside,1,small,2);
    rf_put32(small,0x584e); inside=attr(nested,inside,2,small,outputLength);
    total=attr(out,total,197,nested,inside); rf_put32(out,(uint32_t)total); return total;
}
static int parse(const uint8_t *p,size_t n,uint32_t *value) {
    int32_t error=0; return rf_nl_one_reply(p,n,7,9,35,RF_NL_REGISTER,value,&error);
}
int main(void) {
    uint8_t bytes[128],copy[128],family[128],word[4]; uint32_t value=0; int32_t error=0; size_t n,m;
    static const uint8_t golden[]={
        0x4c,0,0,0, 0x23,0,5,0, 7,0,0,0, 9,0,0,0, 0x67,0,0,0,
        8,0,3,0, 4,0,0,0, 8,0,0xc3,0, 0x18,0x10,0,0, 8,0,0xc4,0, 1,0,0,0,
        0x20,0,0xc5,0, 0x5e,0,0,0, 8,0,0,0, 0x14,0,0,0, 0,0,0,0, 0,0,0,0,
        0x28,0,0,0, 2,0,0,0
    };
    n=rf_nl_register_request(bytes,sizeof(bytes),35,7,9,4,40);
    CHECK(n==sizeof(golden) && memcmp(bytes,golden,n)==0);
    CHECK(rf_nl_register_request(bytes,sizeof(bytes),35,7,9,4,0)==n && rf_le32(bytes+68)==0);
    CHECK(!rf_nl_register_request(bytes,sizeof(bytes),35,7,9,4,30));
    CHECK(!rf_nl_register_request(bytes,sizeof(bytes),35,7,9,4,27));
    CHECK(!rf_nl_register_request(bytes,sizeof(bytes),35,7,9,4,0xffffffffu));
    CHECK(!rf_nl_register_request(bytes,sizeof(bytes),16,7,9,4,40));
    CHECK(!rf_nl_register_request(bytes,sizeof(bytes),35,7,9,0,40));
    CHECK(!rf_nl_register_request(bytes,sizeof(bytes),35,0,9,4,40));
    CHECK(!rf_nl_register_request(bytes,75,35,7,9,4,40));
    n=rf_nl_family_request(bytes,sizeof(bytes),7,9);
    CHECK(n==32 && bytes[16]==3 && rf_le16(bytes+22)==2 && !memcmp(bytes+24,"nl80211",8));
    n=reply(bytes,8); CHECK(parse(bytes,n,&value)==RF_NL_DATA && value==0x584e);
    n=reply(bytes,4); CHECK(parse(bytes,n,&value)==RF_NL_DATA && value==0x584e);
    rf_put32(bytes+8,6); CHECK(parse(bytes,n,&value)==RF_NL_IGNORE);
    rf_put32(bytes+8,7); rf_put32(bytes+12,10); CHECK(parse(bytes,n,&value)==RF_NL_INVALID);
    rf_put32(bytes+12,0); CHECK(parse(bytes,n,&value)==RF_NL_DATA);
    memcpy(copy,bytes,n); copy[16]=102; CHECK(parse(copy,n,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); rf_put16(copy+4,36); CHECK(parse(copy,n,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); rf_put16(copy+20,3); CHECK(parse(copy,n,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); rf_put16(copy+24,40); CHECK(parse(copy,n,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); rf_put16(copy+28,8); CHECK(parse(copy,n,&value)==RF_NL_INVALID);
    CHECK(parse(bytes,n-1,&value)==RF_NL_INVALID);
    CHECK(parse(bytes,15,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); memcpy(copy+n,copy+20,n-20); m=n+n-20; rf_put32(copy,(uint32_t)m);
    CHECK(parse(copy,m,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); rf_put32(word,0x9999); m=attr(copy,n,195,word,4); rf_put32(copy,(uint32_t)m);
    CHECK(parse(copy,m,&value)==RF_NL_INVALID);
    memcpy(copy,bytes,n); rf_put32(word,2); m=attr(copy,n,196,word,4); rf_put32(copy,(uint32_t)m);
    CHECK(parse(copy,m,&value)==RF_NL_INVALID);
    memset(copy,0,sizeof(copy)); rf_put32(copy,20); rf_put16(copy+4,2); rf_put32(copy+8,7);
    CHECK(parse(copy,20,&value)==RF_NL_ACK);
    rf_put32(copy+16,(uint32_t)-22);
    CHECK(rf_nl_one_reply(copy,20,7,9,35,RF_NL_REGISTER,&value,&error)==RF_NL_ERROR && error==-22);
    memset(family,0,sizeof(family)); rf_put16(family+4,16); rf_put32(family+8,7); family[16]=1;
    rf_put16(word,35); m=attr(family,20,1,word,2); m=attr(family,m,2,"nl80211",8); rf_put32(family,(uint32_t)m);
    CHECK(rf_nl_one_reply(family,m,7,9,35,RF_NL_FAMILY,&value,&error)==RF_NL_DATA && value==35);
    family[m-2]='x'; CHECK(rf_nl_one_reply(family,m,7,9,35,RF_NL_FAMILY,&value,&error)==RF_NL_INVALID);
    printf("{\"passed\":%u,\"hardwareRequests\":0}\n",passed); return 0;
}
