#ifndef HBL_RF_NETLINK_WIRE_H
#define HBL_RF_NETLINK_WIRE_H

#include <stdint.h>
#include <stddef.h>
#include <string.h>

/* 绑定原厂 wl 的 nl80211 vendor 封装，只开放本模块 marker 与已准备的单次入口。 */
enum { RF_NL_FAMILY=1, RF_NL_REGISTER=2 };
enum { RF_NL_IGNORE=0, RF_NL_DATA=1, RF_NL_ACK=2, RF_NL_ERROR=-1, RF_NL_INVALID=-2 };
static inline uint16_t rf_le16(const void *p) {
    const uint8_t *b=(const uint8_t *)p; return (uint16_t)(b[0]|((uint16_t)b[1]<<8));
}
static inline uint32_t rf_le32(const void *p) {
    const uint8_t *b=(const uint8_t *)p;
    return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);
}
static inline void rf_put16(void *p,uint16_t n) {
    uint8_t *b=(uint8_t *)p; b[0]=(uint8_t)n; b[1]=(uint8_t)(n>>8);
}
static inline void rf_put32(void *p,uint32_t n) {
    uint8_t *b=(uint8_t *)p;
    b[0]=(uint8_t)n; b[1]=(uint8_t)(n>>8); b[2]=(uint8_t)(n>>16); b[3]=(uint8_t)(n>>24);
}
static inline size_t rf_align4(size_t n) { return (n+3u)&~(size_t)3u; }
static inline size_t rf_nl_begin(uint8_t *out,size_t cap,uint16_t family,uint32_t seq,uint32_t port,uint8_t command) {
    if (cap<20 || !seq) return 0;
    memset(out,0,cap); rf_put32(out,20); rf_put16(out+4,family);
    rf_put16(out+6,5); /* NLM_F_REQUEST | NLM_F_ACK */
    rf_put32(out+8,seq); rf_put32(out+12,port); out[16]=command;
    return 20;
}
static inline int rf_nl_add(uint8_t *out,size_t cap,size_t *used,uint16_t type,const void *data,size_t size) {
    size_t padded;
    if (!used || size>65531 || *used>cap || *used<20) return 0;
    padded=rf_align4(size+4);
    if (padded>cap-*used) return 0;
    rf_put16(out+*used,(uint16_t)(size+4)); rf_put16(out+*used+2,type);
    if (size) memcpy(out+*used+4,data,size);
    *used+=padded; rf_put32(out,(uint32_t)*used); return 1;
}
static inline size_t rf_nl_family_request(uint8_t *out,size_t cap,uint32_t seq,uint32_t port) {
    static const char name[]="nl80211";
    size_t used=rf_nl_begin(out,cap,16,seq,port,3);
    if (!used || !rf_nl_add(out,cap,&used,2,name,sizeof(name))) return 0;
    return used;
}
static inline size_t rf_nl_register_request(uint8_t *out,size_t cap,uint16_t family,uint32_t seq,
                                          uint32_t port,uint32_t ifindex,uint32_t selector) {
    uint8_t value[4],dcmd[28]; size_t used;
    if (family<17 || !ifindex || (selector!=0 && selector!=40)) return 0;
    used=rf_nl_begin(out,cap,family,seq,port,103);
    if (!used) return 0;
    rf_put32(value,ifindex); if (!rf_nl_add(out,cap,&used,3,value,4)) return 0;
    rf_put32(value,0x1018); if (!rf_nl_add(out,cap,&used,195,value,4)) return 0;
    rf_put32(value,1); if (!rf_nl_add(out,cap,&used,196,value,4)) return 0;
    memset(dcmd,0,sizeof(dcmd)); rf_put32(dcmd,94); rf_put32(dcmd+4,8); rf_put32(dcmd+8,20);
    rf_put32(dcmd+20,selector); rf_put32(dcmd+24,2); /* 与 wl phyreg <n> b 相同的 GET、8 字节、band 2。 */
    if (!rf_nl_add(out,cap,&used,197,dcmd,sizeof(dcmd))) return 0;
    return used;
}

/* 找单一属性；完整检查属性区，拒绝重复目标属性和截断。 */
static inline int rf_nl_attribute(const uint8_t *p,size_t size,uint16_t wanted,const uint8_t **data,size_t *length) {
    int found=0;
    *data=NULL; *length=0;
    while (size) {
        size_t n,aligned; uint16_t type;
        if (size<4) return -1;
        n=rf_le16(p); type=rf_le16(p+2)&0x3fff;
        if (n<4 || n>size) return -1;
        aligned=rf_align4(n);
        if (aligned>size) return -1;
        if (type==wanted) {
            if (found) return -1;
            found=1; *data=p+4; *length=n-4;
        }
        p+=aligned; size-=aligned;
    }
    return found;
}
static inline int rf_nl_one_reply(const uint8_t *msg,size_t size,uint32_t seq,uint32_t port,
                                  uint16_t family,int operation,uint32_t *value,int32_t *error) {
    const uint8_t *data,*second; size_t length,secondLength; int present;
    uint16_t type;
    if (size<16 || rf_le32(msg)!=size) return RF_NL_INVALID;
    if (rf_le32(msg+8)!=seq) return RF_NL_IGNORE;
    if (rf_le32(msg+12)!=0 && rf_le32(msg+12)!=port) return RF_NL_INVALID;
    type=rf_le16(msg+4);
    if (type==2) {
        if (size<20) return RF_NL_INVALID;
        *error=(int32_t)rf_le32(msg+16);
        return *error ? RF_NL_ERROR : RF_NL_ACK;
    }
    if (size<20 || type!=(operation==RF_NL_FAMILY ? 16 : family)) return RF_NL_INVALID;
    if (operation==RF_NL_FAMILY) {
        if (msg[16]!=1 && msg[16]!=3) return RF_NL_INVALID;
        if (rf_nl_attribute(msg+20,size-20,1,&data,&length)!=1 || length!=2) return RF_NL_INVALID;
        *value=rf_le16(data);
        if (*value<17) return RF_NL_INVALID;
        if (rf_nl_attribute(msg+20,size-20,2,&data,&length)!=1 || length!=8 || memcmp(data,"nl80211",8)) return RF_NL_INVALID;
        return RF_NL_DATA;
    }
    if (operation!=RF_NL_REGISTER || msg[16]!=103) return RF_NL_INVALID;
    present=rf_nl_attribute(msg+20,size-20,195,&data,&length);
    if (present<0 || (present && (length!=4 || rf_le32(data)!=0x1018))) return RF_NL_INVALID;
    present=rf_nl_attribute(msg+20,size-20,196,&data,&length);
    if (present<0 || (present && (length!=4 || rf_le32(data)!=1))) return RF_NL_INVALID;
    if (rf_nl_attribute(msg+20,size-20,197,&data,&length)!=1) return RF_NL_INVALID;
    if (rf_nl_attribute(data,length,1,&second,&secondLength)!=1 || secondLength!=2) return RF_NL_INVALID;
    {
        const size_t declared=rf_le16(second);
        if (declared!=4 && declared!=8) return RF_NL_INVALID;
        if (rf_nl_attribute(data,length,2,&second,&secondLength)!=1 || secondLength!=declared) return RF_NL_INVALID;
        *value=rf_le32(second)&0xffffu;
    }
    return RF_NL_DATA;
}
#endif
