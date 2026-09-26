#ifndef HBL_MECHANICAL_PREPARED_REQUEST_H
#define HBL_MECHANICAL_PREPARED_REQUEST_H
#include "rf_netlink_wire.h"
typedef struct {
    uint8_t bytes[128];
    size_t size;
    uint32_t sequence;
    unsigned ready;
} MechanicalPreparedRequest;
/* 每次准备/上次响应成功后预编码下一次唯一请求；触发时不再构建属性。 */
static inline int mechanical_prepare_request(MechanicalPreparedRequest *p,uint16_t family,
                                             uint32_t previous,uint32_t port,uint32_t interfaceIndex) {
    p->ready=0; p->size=0;
    if (previous==UINT32_MAX) return 0;
    p->sequence=previous+1;
    p->size=rf_nl_register_request(p->bytes,sizeof(p->bytes),family,p->sequence,port,interfaceIndex,40);
    p->ready=p->size!=0;
    return p->ready;
}
static inline int mechanical_consume_request(MechanicalPreparedRequest *p,uint32_t previous) {
    if (!p->ready || previous==UINT32_MAX || p->sequence!=previous+1) return 0;
    p->ready=0;
    return 1;
}
#endif
