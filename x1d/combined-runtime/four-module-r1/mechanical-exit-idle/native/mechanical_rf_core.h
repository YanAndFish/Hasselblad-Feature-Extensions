#ifndef HBL_MECHANICAL_RF_CORE_H
#define HBL_MECHANICAL_RF_CORE_H
#include <stdint.h>
#include <string.h>
#include "mechanical_sync_wire.h"
typedef struct {
    unsigned enabled,source,delay_us,pending,consumed,progress_threshold;
    uint32_t trial;
    uint64_t last_us,deadline_us;
} RfCore;
static inline void rf_init(RfCore *c,uint32_t unused) {
    (void)unused; memset(c,0,sizeof(*c)); c->source=3;
}
static inline void rf_cancel(RfCore *c) { c->pending=0; c->consumed=1; }
static inline int rf_configure(RfCore *c,unsigned on,unsigned source,unsigned delay) {
    if (on>1 || source>=HBL_MECH_SOURCES || delay>5000000 || delay%10) return 0;
    if (c->enabled!=on || c->source!=source || c->delay_us!=delay) rf_cancel(c);
    c->enabled=on; c->source=source; c->delay_us=delay;
    return 1;
}
static inline void mechanical_rf_begin(RfCore *c,uint32_t trial) {
    if (trial>c->trial) {
        c->pending=0; c->consumed=0; c->trial=trial;
    }
}
static inline int rf_progress_configure(RfCore *c,unsigned unused) {
    (void)unused; c->progress_threshold=0; return 1;
}
static inline int mechanical_rf_accept(RfCore *c,const struct HblMechanicalSync *s,
                                       uint64_t at,uint64_t now,uint64_t armed_at) {
    mechanical_rf_begin(c,s->trial);
    if (s->trial==c->trial && at<armed_at) { rf_cancel(c); return 0; }
    if (s->trial!=c->trial || !c->enabled || c->consumed || at<armed_at || at>now || now-at>250000 ||
        now<c->last_us || at>UINT64_MAX-c->delay_us || !hbl_mech_confirmed(s,c->source)) return 0;
    c->last_us=now; c->consumed=1; c->pending=1; c->trial=s->trial;
    c->deadline_us=at+c->delay_us;
    return 1;
}
static inline int rf_due(RfCore *c,uint64_t now) {
    if (now<c->last_us) { rf_cancel(c); c->enabled=0; return 0; }
    c->last_us=now;
    if (!c->enabled || !c->pending || now<c->deadline_us) return 0;
    c->pending=0; /* 本请求资格已消费；保持开关，下一请求可再次引闪。 */
    return now-c->deadline_us<=250000;
}
/* 截止点附近暂缓界面状态构造；长延迟仍正常回复心跳，不修改发射/取消资格。 */
static inline int mechanical_defer_status(const RfCore *c,uint64_t now) {
    return c->pending && (now>=c->deadline_us || c->deadline_us-now<=2000);
}
#endif
