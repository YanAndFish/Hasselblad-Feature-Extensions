#include "../native/formal_prepared_request.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned checks;
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"line %d: %s\n",__LINE__,#x); exit(1); } ++checks; } while (0)
static size_t attr(uint8_t *out,size_t off,uint16_t type,const void *bytes,size_t size) {
    rf_put16(out+off,(uint16_t)(size+4));rf_put16(out+off+2,type);memcpy(out+off+4,bytes,size);return off+rf_align4(size+4);
}
static size_t reply(uint8_t *out) {
    uint8_t nested[32]={0},word[8]={0};size_t inside=0,used=20;
    memset(out,0,128);rf_put16(out+4,35);rf_put32(out+8,7);rf_put32(out+12,99);out[16]=103;
    rf_put16(word,4);inside=attr(nested,inside,1,word,2);
    rf_put32(word,0x5854);inside=attr(nested,inside,2,word,4);
    used=attr(out,used,197,nested,inside);rf_put32(out,(uint32_t)used);return used;
}
static int parse(const uint8_t *p,size_t n) { uint32_t value=0;int32_t error=0;return rf_nl_one_reply(p,n,7,99,35,RF_NL_REGISTER,&value,&error); }
int main(void) {
    uint8_t bytes[128],fire[128],copy[128];unsigned allowed=0;
    CHECK(formal_nl_register_request(bytes,sizeof(bytes),35,7,99,4,40)==76);
    CHECK(rf_nl_register_request(fire,sizeof(fire),35,7,99,4,40)==76);
    CHECK(memcmp(bytes,fire,76)==0);
    for (unsigned selector=0;selector<65536;++selector) {
        const int expected=selector==0 || (selector>=14 && selector<=20) || selector==26 || selector==27 ||
            selector==40 || selector==48 || (selector>=512 && selector<512+HBL_FORMAL_CONTROL_WAVES) ||
            (selector>=HBL_FORMAL_CONFIG_BASE && selector<HBL_FORMAL_CONFIG_BASE+HBL_FORMAL_CONFIG_COUNT);
        const size_t size=formal_nl_register_request(bytes,sizeof(bytes),35,7,99,4,selector);
        CHECK(formal_selector_allowed(selector)==expected);
        CHECK(expected ? size==76 && rf_le32(bytes+68)==selector && rf_le32(bytes+72)==2 : size==0);
        if (expected) ++allowed;
    }
    CHECK(allowed==4556);
    CHECK(!formal_nl_register_request(bytes,sizeof(bytes),35,7,99,4,UINT32_MAX));
    CHECK(!formal_nl_register_request(NULL,sizeof(bytes),35,7,99,4,14));
    CHECK(!formal_nl_register_request(bytes,75,35,7,99,4,14));
    CHECK(!formal_nl_register_request(bytes,sizeof(bytes),16,7,99,4,14));
    CHECK(!formal_nl_register_request(bytes,sizeof(bytes),35,0,99,4,14));
    CHECK(!formal_nl_register_request(bytes,sizeof(bytes),35,7,99,0,14));
    for (unsigned index=0;index<HBL_FORMAL_WAVES;++index) {
        const uint32_t low=hbl_formal_hashes[index]&65535,high=hbl_formal_hashes[index]>>16;
        CHECK(formal_selection_verified(index,low,high,1,index));
        CHECK(!formal_selection_verified(index,low^1,high,1,index));
        CHECK(!formal_selection_verified(index,low,high^1,1,index));
        CHECK(!formal_selection_verified(index,low,high,0,index));
        CHECK(!formal_selection_verified(index,low,high,2,index));
        CHECK(!formal_selection_verified(index,low,high,1,(index+1)%HBL_FORMAL_WAVES));
        CHECK(!formal_selection_verified(index,low+65536,high,1,index));
        CHECK(!formal_selection_verified(index,low,high+65536,1,index));
        FormalPreparedRequest request={0};
        CHECK(formal_prepare_request(&request,35,7,99,4,index)==(index==HBL_FORMAL_FIRE_INDEX));
        if (index==HBL_FORMAL_FIRE_INDEX) {
            CHECK(request.ready && request.sequence==8 && request.size==76 && rf_le32(request.bytes+68)==40);
            CHECK(!formal_consume_request(&request,6) && request.ready);
            CHECK(formal_consume_request(&request,7) && !request.ready);
            CHECK(!formal_consume_request(&request,7));
        }
    }
    CHECK(!formal_selection_verified(HBL_FORMAL_WAVES,0,0,1,HBL_FORMAL_WAVES));
    CHECK(!formal_selection_verified(UINT32_MAX,0,0,1,UINT32_MAX));
    FormalPreparedRequest prepared={0};
    CHECK(!formal_prepare_request(NULL,35,0,99,4,HBL_FORMAL_FIRE_INDEX));
    CHECK(!formal_consume_request(NULL,0));
    CHECK(!formal_prepare_request(&prepared,35,UINT32_MAX,99,4,HBL_FORMAL_FIRE_INDEX));
    CHECK(formal_prepare_request(&prepared,35,UINT32_MAX-1,99,4,HBL_FORMAL_FIRE_INDEX));
    CHECK(formal_consume_request(&prepared,UINT32_MAX-1));
    CHECK(!formal_consume_request(&prepared,UINT32_MAX));
    const size_t size=reply(bytes);CHECK(parse(bytes,size)==RF_NL_DATA);
    memcpy(copy,bytes,size);rf_put32(copy+8,8);CHECK(parse(copy,size)==RF_NL_IGNORE);
    memcpy(copy,bytes,size);rf_put32(copy+12,100);CHECK(parse(copy,size)==RF_NL_INVALID);
    memcpy(copy,bytes,size);copy[16]=102;CHECK(parse(copy,size)==RF_NL_INVALID);
    memcpy(copy,bytes,size);rf_put16(copy+20,3);CHECK(parse(copy,size)==RF_NL_INVALID);
    memcpy(copy,bytes,size);rf_put16(copy+24,40);CHECK(parse(copy,size)==RF_NL_INVALID);
    memcpy(copy,bytes,size);rf_put16(copy+28,8);CHECK(parse(copy,size)==RF_NL_INVALID);
    CHECK(parse(bytes,size-1)==RF_NL_INVALID);
    memcpy(copy,bytes,size);memcpy(copy+size,copy+20,size-20);rf_put32(copy,(uint32_t)(size*2-20));
    CHECK(parse(copy,size*2-20)==RF_NL_INVALID);
    memset(copy,0,sizeof(copy));rf_put32(copy,20);rf_put16(copy+4,2);rf_put32(copy+8,7);
    CHECK(parse(copy,20)==RF_NL_ACK);
    rf_put32(copy+16,(uint32_t)-22);CHECK(parse(copy,20)==RF_NL_ERROR);
    printf("formal-radio-wire-checks=%u hardware-requests=0\n",checks);return 0;
}
