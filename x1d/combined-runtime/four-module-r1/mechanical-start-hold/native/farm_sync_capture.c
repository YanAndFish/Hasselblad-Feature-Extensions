/* 固定 X1D 1.25.0 FARM 离线候选；未安装。
 * 清旧标志 -> 正常启动/定时 -> 读 FPGA 保持位 -> 零等待投递一次。
 * 不写传感器参数，不配置计时器，不调用拍摄或无线函数。
 */
#include <stdint.h>
#include "farm_sync_wire.h"

struct HblSyncRecord {
    uint32_t magic, enabled, stage, sequence;
    struct HblFarmSync sample;
    uint32_t queued, dropped;
    uint32_t packet[72]; /* 原厂队列复制 287 字节，全部初始化。 */
};
_Static_assert(sizeof(struct HblFarmSync)==44,"sync payload layout");
_Static_assert(sizeof(struct HblSyncRecord)==356,"sync record layout");

static uint32_t read32(uint32_t a) { return *(volatile const uint32_t *)(uintptr_t)a; }
static int enabled(volatile struct HblSyncRecord *out) {
    return out && !((uintptr_t)out&3) && out->magic==HBL_SYNC_MAGIC && out->enabled==1;
}
static void count(volatile uint32_t *v) { if (*v!=UINT32_MAX) ++*v; }

/* 只由已经匹配 ES 调用者、cmd=0、mode=0 的汇编包装调用。
 * 返回值替换原 control=0；下一条原厂 control=3 仍照常执行。
 */
__attribute__((used,visibility("default")))
uint32_t farm_sync_begin(volatile struct HblSyncRecord *out) {
    if (!enabled(out)) return 0;
    out->stage=0;
    if (out->sequence==UINT32_MAX) { out->enabled=0; return 0; }
    ++out->sequence;
    out->sample.magic=HBL_SYNC_MAGIC;
    out->sample.version=3;
    out->sample.shot=out->sequence;
    out->sample.flags=0;
    out->sample.cleared_status=out->sample.sync_status=0;
    out->sample.timer_low=out->sample.timer_high=out->sample.timer_control=0;
    out->sample.exposure_low=out->sample.exposure_high=0;
    out->stage=1;
    return 0x40; /* 控制 bit6，独立于状态 bit10。 */
}

__attribute__((used,visibility("default")))
void farm_sync_cleared(volatile struct HblSyncRecord *out) {
    if (!enabled(out) || out->stage!=1) return;
    const uint32_t status=read32(UINT32_C(0x42000014));
    out->sample.cleared_status=status;
    if (!(status&HBL_SYNC_STATUS_BIT)) out->sample.flags=HBL_SYNC_CLEAR;
    out->stage=2;
}

static void sample_clock(volatile struct HblFarmSync *out) {
    const uint32_t base=UINT32_C(0xf8f00200);
    const uint32_t control=read32(base+8);
    out->timer_control=control;
    if (!(control&1)) return;
    for (unsigned i=0;i<4;++i) {
        const uint32_t hi=read32(base+4),lo=read32(base);
        if (hi==read32(base+4)) {
            if (control==read32(base+8)) {
                out->timer_low=lo; out->timer_high=hi; out->flags|=HBL_SYNC_CLOCK;
            }
            return;
        }
    }
}

static void publish(volatile struct HblSyncRecord *out) {
    sample_clock(&out->sample);
    for (unsigned i=0;i<72;++i) out->packet[i]=0;
    out->packet[0]=UINT32_C(0x05010009);
    const volatile uint32_t *fields=(const volatile uint32_t *)&out->sample;
    for (unsigned i=0;i<11;++i) out->packet[i+1]=fields[i];
    __asm__ volatile("dmb sy" ::: "memory");
    const uint32_t queue=read32(UINT32_C(0x006c4df4));
    if (!queue || (queue&3)) { count(&out->dropped); return; }
    typedef int (*QueueSend)(uint32_t,const void *,uint32_t,uint32_t);
    const QueueSend send=(QueueSend)(uintptr_t)UINT32_C(0x00186500);
    if (send(queue,(const void *)out->packet,0,0)==1) count(&out->queued);
    else count(&out->dropped);
}

/* B 的单次检查点保持原位置；未确认 B 不产生其后续候选事件。 */
__attribute__((used,visibility("default")))
void farm_sync_observe(volatile struct HblSyncRecord *out, uint32_t exposure_low, uint32_t exposure_high) {
    if (!enabled(out) || out->stage!=2) return;
    out->stage=3;
    out->sample.exposure_low=exposure_low;
    out->sample.exposure_high=exposure_high;
    out->sample.sync_status=read32(UINT32_C(0x42000014));
    if ((out->sample.flags&HBL_SYNC_CLEAR) && (out->sample.sync_status&HBL_SYNC_STATUS_BIT))
        out->sample.flags|=HBL_SYNC_SEEN;
    publish(out);
    if (out->sample.flags!=7) out->stage=0;
}

/* 原厂进度函数已经返回。只转发严格增加的读数，不增加轮询或延时。
 * 达到原厂退出门限 100 后不再转发；最多 51 个偶数读数。
 */
__attribute__((used,visibility("default")))
void farm_sync_progress(volatile struct HblSyncRecord *out, uint32_t value) {
    if (!enabled(out) || (out->stage!=3 && out->stage!=4)) return;
    if (out->stage==4 && (out->sample.cleared_status>=100 || value<=out->sample.cleared_status)) return;
    out->sample.cleared_status=value;
    out->stage=4;
    out->sample.flags=0x100u|HBL_SYNC_CLEAR|HBL_SYNC_SEEN;
    out->sample.sync_status=read32(UINT32_C(0x42000014));
    out->sample.timer_low=out->sample.timer_high=out->sample.timer_control=0;
    publish(out);
}

/* 仅原厂正常停止调用之前；超时停止不会经过此入口。 */
__attribute__((used,visibility("default")))
void farm_sync_stop(volatile struct HblSyncRecord *out) {
    if (!enabled(out) || out->stage!=4) return;
    out->stage=5;
    out->sample.flags=0x200u|HBL_SYNC_CLEAR|HBL_SYNC_SEEN;
    out->sample.sync_status=read32(UINT32_C(0x42000014));
    out->sample.timer_low=out->sample.timer_high=out->sample.timer_control=0;
    publish(out);
}
