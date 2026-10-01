/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#ifndef X2D_SUBJECT_TRACKER_H
#define X2D_SUBJECT_TRACKER_H
#include <stddef.h>
#include <stdint.h>

/* 离线候选：调用方串行提交事件。无设备访问、模型加载或镜头操作。 */
typedef struct { int x, y, w, h; } StRect;
typedef struct {
    const unsigned char *pixels;
    size_t bytes;
    int width, height, stride;
    uint64_t id, time_ms, layout;
} StFrame;
typedef struct { uint64_t epoch, request, frame_id, time_ms, layout; } StTicket;
typedef enum { ST_PERSON=1, ST_BIRD, ST_DOG, ST_VEHICLE } StKind;
typedef enum {
    ST_OK=0, ST_INVALID, ST_STALE, ST_WRONG_EPOCH, ST_BUSY,
    ST_OUTSIDE_SELECTION, ST_NO_MATCH, ST_AMBIGUOUS, ST_LOST, ST_CLASS_CHANGED
} StResult;
typedef struct {
    unsigned max_detection_age_ms, max_roi_age_ms;
    int search_radius, selection_radius;
    double min_similarity, ambiguity_margin;
} StConfig;
typedef struct {
    StRect box;
    StKind kind;
    uint64_t frame_id, time_ms, epoch;
    double similarity;
} StRoi;
typedef struct {
    StConfig config;
    int width, height, manual_x, manual_y, selected, locked, detection_pending;
    uint64_t layout, epoch, request, detection_time_ms;
    double reference[256];
    double reference_energy;
    StRoi roi;
} StTracker;

StResult st_init(StTracker *, int width, int height, uint64_t layout, StConfig);
StResult st_select(StTracker *, int x, int y);
StResult st_begin_detection(StTracker *, const StFrame *, StTicket *);
StResult st_cancel_detection(StTracker *, StTicket);
/* source 是第一层处理的原帧；current 是交接时的新帧，不直接输出旧框。 */
StResult st_accept_detection(StTracker *, StTicket, const StFrame *source,
                             StRect source_box, StKind, const StFrame *current);
StResult st_track(StTracker *, const StFrame *current);
StResult st_get_roi(const StTracker *, uint64_t now_ms, StRoi *);
#endif
