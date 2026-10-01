/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#ifndef EYE_AFS_TARGET_EXCHANGE_H
#define EYE_AFS_TARGET_EXCHANGE_H
#include "proxy_bridge.h"

/* One detector writer, one camera reader. Fixed little-endian ARM32 layout.
 * Initialize before either process maps it; never truncate a mapped file.
 * The detector alone writes sequence and target words. The future loader
 * owns the binding words and last-dispatch observation, not target input.
 */
#define EAF_TARGET_MAGIC 0x45414654u
#define EAF_TARGET_VERSION 2u
typedef struct {
    uint32_t sequence,dispatch_count,user_point,point,size,timeout,kind,reason;
    uint32_t watcher_nonnull,generation,received_lo,received_hi,decision_lo,decision_hi;
} EafRequestObservation;
typedef struct {
    uint32_t magic,version,sequence;
    uint32_t mode,current_generation,received_lo,received_hi,target_generation;
    uint32_t face_count,face_point,eye_point,qualification;
    uint32_t bound_pid,owner_tid;
    EafRequestObservation observation;
} EafTargetExchange;

void eaf_target_init(EafTargetExchange *p);
/* NULL target explicitly invalidates the old detection without waiting for
 * its age limit. A crashed writer's odd sequence is not silently repaired.
 */
int eaf_target_publish(EafTargetExchange *p,enum EafMode mode,
                        uint32_t current_generation,const EafTargetSnapshot *target);
/* One attempt, no retry/spin/wait. Does not set current camera mode, time or
 * age policy: the camera-side reader must supply those from its own context.
 * Copy failure leaves out unchanged; no partial target becomes visible.
 */
int eaf_target_read(const EafTargetExchange *p,EafTriggerSnapshot *out);
/* One camera-owner-thread writer. Counts returned native calls; no success,
 * sensor/AF execution, or optical-quality claim. The detector never writes it.
 */
int eaf_observation_publish(EafTargetExchange *p,uint32_t user_point,
                            const EafRequest *request,int timeout,
                            const EafTriggerSnapshot *snapshot,void *watcher);
int eaf_observation_read(const EafTargetExchange *p,EafRequestObservation *out);
#endif
