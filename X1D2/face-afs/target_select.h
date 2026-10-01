/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#ifndef EYE_AFS_TARGET_SELECT_H
#define EYE_AFS_TARGET_SELECT_H
#include "af_request.h"

typedef struct {
    int score,x,y,width,height;
    int landmarks[10]; /* image-left eye, image-right eye, nose, mouth corners */
} EafRawFace;

/* Initial controlled-test policy for the measured 160x120 backend. These are
 * conservative heuristics, not calibrated probabilities or eye confidence.
 * geometry_approved is an external acquisition gate, never inferred from a
 * high detector score. eye_index 0/1 explicitly selects an image-side eye.
 */
EafTargetSnapshot eaf_select_target(const EafRawFace *faces,uint32_t count,
                                   uint64_t received_ns,uint32_t generation,
                                   unsigned geometry_approved,unsigned eye_index);
#endif
