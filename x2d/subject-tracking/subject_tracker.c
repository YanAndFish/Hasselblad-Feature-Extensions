/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#include "subject_tracker.h"
#include <math.h>
#include <string.h>

/* 16x16 灰度模板，整数平移搜索；不宣称具备尺度/姿态不变性或神经模型精度。 */
static int frame_valid(const StTracker *s, const StFrame *f) {
    if (!s || !f || !f->pixels || f->width != s->width || f->height != s->height ||
        f->layout != s->layout || f->stride < f->width || f->stride > 65536) return 0;
    return f->bytes >= (size_t)(f->height-1)*(size_t)f->stride+(size_t)f->width;
}
static int rect_valid(const StTracker *s, StRect r) {
    return r.w >= 4 && r.h >= 4 && r.w <= s->width && r.h <= s->height &&
           r.x >= 0 && r.y >= 0 && r.x <= s->width-r.w && r.y <= s->height-r.h;
}
static double sample(const StFrame *f, StRect r, double *values) {
    double sum=0, energy=0;
    for (int y=0; y<16; ++y) for (int x=0; x<16; ++x) {
        int px=r.x+((2*x+1)*r.w)/32, py=r.y+((2*y+1)*r.h)/32;
        double v=f->pixels[(size_t)py*(size_t)f->stride+(size_t)px];
        values[y*16+x]=v; sum+=v;
    }
    sum/=256;
    for (int i=0; i<256; ++i) { values[i]-=sum; energy+=values[i]*values[i]; }
    return energy;
}
static double score(const StTracker *s, const StFrame *f, StRect r) {
    double values[256], energy=sample(f,r,values), dot=0;
    if (energy<256*4 || s->reference_energy<256*4) return 0;
    for (int i=0; i<256; ++i) dot+=values[i]*s->reference[i];
    if (dot<=0) return 0;
    double result=dot/sqrt(energy*s->reference_energy);
    return result>1 ? 1 : result;
}
static int imax(int a,int b) { return a>b ? a:b; }
static int imin(int a,int b) { return a<b ? a:b; }
static StResult match(const StTracker *s,const StFrame *f,StRect around,StRoi *out) {
    int radius=s->config.search_radius;
    int xmin=imax(0,around.x-radius), xmax=imin(s->width-around.w,around.x+radius);
    int ymin=imax(0,around.y-radius), ymax=imin(s->height-around.h,around.y+radius);
    double scores[65*65],best=-1,second=-1;
    StRect chosen=around; int count=0;
    for(int y=ymin;y<=ymax;++y) for(int x=xmin;x<=xmax;++x) {
        StRect r={x,y,around.w,around.h}; double v=score(s,f,r);
        scores[count++]=v;
        if(v>best) { best=v; chosen=r; }
    }
    if(best<s->config.min_similarity) return ST_NO_MATCH;
    /* 同一响应峰的邻近点不是第二个主体；分离的近似峰则拒绝二选一。 */
    int exclusion=imax(1,imin(around.w,around.h)/4); count=0;
    for(int y=ymin;y<=ymax;++y) for(int x=xmin;x<=xmax;++x) {
        double v=scores[count++];
        if ((x<chosen.x-exclusion || x>chosen.x+exclusion ||
             y<chosen.y-exclusion || y>chosen.y+exclusion) && v>second) second=v;
    }
    if(second>=0 && best-second<s->config.ambiguity_margin) return ST_AMBIGUOUS;
    *out=(StRoi){chosen,s->roi.kind,f->id,f->time_ms,s->epoch,best};
    return ST_OK;
}
StResult st_init(StTracker *s,int w,int h,uint64_t layout,StConfig c) {
    if(!s || w<4 || h<4 || w>8192 || h>8192 || c.search_radius<1 || c.search_radius>32 ||
       c.selection_radius<0 || c.selection_radius>8192 || !c.max_detection_age_ms ||
       !c.max_roi_age_ms || !isfinite(c.min_similarity) || !isfinite(c.ambiguity_margin) ||
       c.min_similarity<=0 || c.min_similarity>1 || c.ambiguity_margin<=0 || c.ambiguity_margin>1)
        return ST_INVALID;
    memset(s,0,sizeof(*s)); s->width=w;s->height=h;s->layout=layout;s->config=c;
    return ST_OK;
}
StResult st_select(StTracker *s,int x,int y) {
    if(!s || x<0 || y<0 || x>=s->width || y>=s->height || s->epoch==UINT64_MAX) return ST_INVALID;
    s->manual_x=x;s->manual_y=y;s->selected=1;s->locked=0;s->detection_pending=0;++s->epoch;
    return ST_OK;
}
StResult st_begin_detection(StTracker *s,const StFrame *f,StTicket *out) {
    if(!frame_valid(s,f) || !out || !s->selected || s->request==UINT64_MAX) return ST_INVALID;
    if(s->locked && (f->id<s->roi.frame_id || f->time_ms<s->roi.time_ms)) return ST_STALE;
    if(s->detection_pending) {
        if(f->time_ms<s->detection_time_ms) return ST_STALE;
        if(f->time_ms-s->detection_time_ms<=s->config.max_detection_age_ms) return ST_BUSY;
    }
    s->detection_pending=1;s->detection_time_ms=f->time_ms;
    *out=(StTicket){s->epoch,++s->request,f->id,f->time_ms,f->layout};
    return ST_OK;
}
StResult st_cancel_detection(StTracker *s,StTicket t) {
    if(!s) return ST_INVALID;
    if(!s->detection_pending || t.epoch!=s->epoch || t.request!=s->request) return ST_WRONG_EPOCH;
    s->detection_pending=0;return ST_OK;
}
StResult st_accept_detection(StTracker *s,StTicket t,const StFrame *src,StRect box,
                             StKind kind,const StFrame *now) {
    if(!s) return ST_INVALID;
    if(t.epoch!=s->epoch || t.request!=s->request || !t.request || !s->detection_pending) return ST_WRONG_EPOCH;
    s->detection_pending=0; /* 每份结果仅消费一次，错误也不积压在请求槽内。 */
    if(!frame_valid(s,src) || !frame_valid(s,now) || !s->selected || !rect_valid(s,box) ||
       kind<ST_PERSON || kind>ST_VEHICLE) return ST_INVALID;
    if(t.frame_id!=src->id || t.time_ms!=src->time_ms || t.layout!=src->layout) return ST_INVALID;
    if(now->id<src->id || now->time_ms<src->time_ms ||
       now->time_ms-src->time_ms>s->config.max_detection_age_ms) return ST_STALE;
    if(s->locked && (now->id<s->roi.frame_id || now->time_ms<s->roi.time_ms)) return ST_STALE;
    if(s->locked && kind!=s->roi.kind) return ST_CLASS_CHANGED;
    int dx=imax(imax(box.x-s->manual_x,s->manual_x-(box.x+box.w-1)),0);
    int dy=imax(imax(box.y-s->manual_y,s->manual_y-(box.y+box.h-1)),0);
    if(!s->locked && dx*dx+dy*dy>s->config.selection_radius*s->config.selection_radius) return ST_OUTSIDE_SELECTION;
    if(s->locked && score(s,src,box)<s->config.min_similarity) return ST_NO_MATCH;
    StTracker candidate=*s;
    candidate.reference_energy=sample(src,box,candidate.reference);
    candidate.roi.kind=kind;
    StRect around=s->locked ? s->roi.box : box;
    /* 当前实验固定尺度；检测框尺度改变暂不偷偷改变跟踪模板几何。 */
    if(s->locked && (box.w!=around.w || box.h!=around.h)) return ST_INVALID;
    StResult result=match(&candidate,now,around,&candidate.roi);
    if(result!=ST_OK) return result;
    candidate.locked=1;*s=candidate; return ST_OK;
}
StResult st_track(StTracker *s,const StFrame *now) {
    if(!frame_valid(s,now)) return ST_INVALID;
    if(!s->locked) return ST_LOST;
    if(now->id<=s->roi.frame_id || now->time_ms<=s->roi.time_ms) return ST_STALE;
    StRoi next;
    StResult r=now->time_ms-s->roi.time_ms>s->config.max_roi_age_ms ? ST_STALE : match(s,now,s->roi.box,&next);
    if(r!=ST_OK) { s->locked=0;s->detection_pending=0; if(s->epoch!=UINT64_MAX) ++s->epoch; return r; }
    s->roi=next;return ST_OK;
}
StResult st_get_roi(const StTracker *s,uint64_t time,StRoi *out) {
    if(!s || !out) return ST_INVALID;
    if(!s->locked) return ST_LOST;
    if(time<s->roi.time_ms || time-s->roi.time_ms>s->config.max_roi_age_ms) return ST_STALE;
    *out=s->roi;return ST_OK;
}
