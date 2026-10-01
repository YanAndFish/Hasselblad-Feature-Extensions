/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#include "subject_tracker.h"
#include <stdlib.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

enum { W=128,H=96 };
static unsigned char source[W*H],current[W*H],patch[16*16];
static StTracker tracker;
static unsigned checks;
#define CHECK(x) do { ++checks; if(!(x)) { fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); return 1; } } while(0)
static StFrame frame(unsigned char *p,uint64_t id,uint64_t time) {
    return (StFrame){p,W*H,W,H,W,id,time,1};
}
static void put(unsigned char *p,int x,int y,int brighten) {
    for(int j=0;j<16;++j) for(int i=0;i<16;++i) p[(y+j)*W+x+i]=(unsigned char)(patch[j*16+i]+brighten);
}
static StTicket reset(void) {
    StConfig config={250,80,24,4,0.90,0.08};
    if(st_init(&tracker,W,H,1,config)!=ST_OK || st_select(&tracker,40,40)!=ST_OK) abort();
    memset(source,17,sizeof(source));memset(current,17,sizeof(current));
    put(source,32,32,0);
    StTicket t; StFrame f=frame(source,10,1000);
    if(st_begin_detection(&tracker,&f,&t)!=ST_OK) abort();return t;
}
static StTicket rearm(StFrame f) {
    StTicket t;
    if(st_begin_detection(&tracker,&f,&t)!=ST_OK) abort();return t;
}
int main(void) {
    unsigned seed=5729;
    for(unsigned i=0;i<sizeof(patch);++i) { seed=1664525*seed+1013904223;patch[i]=(unsigned char)(40+(seed>>24)%160); }
    StRect initial={32,32,16,16}; StRoi roi;
    StTicket ticket=reset();StFrame src=frame(source,10,1000),now=frame(current,16,1200);
    put(current,45,36,0);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_OK);
    CHECK(st_get_roi(&tracker,1200,&roi)==ST_OK);
    CHECK(roi.box.x==45 && roi.box.y==36 && roi.frame_id==16); /* 旧检测实际匹配到新位置。 */
    CHECK(tracker.manual_x==40 && tracker.manual_y==40);
    CHECK(st_begin_detection(&tracker,&now,&ticket)==ST_OK);
    StTicket ignored;
    CHECK(st_begin_detection(&tracker,&now,&ignored)==ST_BUSY);
    memset(current,17,sizeof(current));put(current,51,41,20);now=frame(current,17,1233);
    CHECK(st_track(&tracker,&now)==ST_OK);
    CHECK(st_get_roi(&tracker,1233,&roi)==ST_OK && roi.box.x==51 && roi.box.y==41);
    CHECK(st_track(&tracker,&now)==ST_STALE);
    CHECK(st_get_roi(&tracker,1314,&roi)==ST_STALE);
    CHECK(st_get_roi(&tracker,1200,&roi)==ST_STALE);
    memset(current,17,sizeof(current));now=frame(current,18,1266);
    CHECK(st_track(&tracker,&now)==ST_NO_MATCH);
    CHECK(st_get_roi(&tracker,1266,&roi)==ST_LOST);
    CHECK(tracker.manual_x==40 && tracker.manual_y==40);

    ticket=reset();put(current,44,36,0);now=frame(current,16,1200);
    CHECK(st_select(&tracker,90,40)==ST_OK);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_WRONG_EPOCH);
    CHECK(st_get_roi(&tracker,1200,&roi)==ST_LOST);

    ticket=reset();StTicket newer;
    CHECK(st_begin_detection(&tracker,&src,&newer)==ST_BUSY);
    CHECK(st_cancel_detection(&tracker,ticket)==ST_OK);
    CHECK(st_begin_detection(&tracker,&src,&newer)==ST_OK);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_WRONG_EPOCH);
    ticket=reset();put(current,44,36,0);now=frame(current,16,1251);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_STALE);
    ticket=rearm(src);now=frame(current,9,999);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_STALE);
    ticket=rearm(src);now=frame(current,16,1200);StFrame wrong=src;wrong.id=11;
    CHECK(st_accept_detection(&tracker,ticket,&wrong,initial,ST_PERSON,&now)==ST_INVALID);
    ticket=rearm(src);wrong=now;wrong.layout=2;
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&wrong)==ST_INVALID);
    ticket=rearm(src);wrong=now;wrong.bytes=12;
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&wrong)==ST_INVALID);
    ticket=rearm(src);wrong=now;wrong.stride=-1;
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&wrong)==ST_INVALID);
    ticket=rearm(src);
    CHECK(st_accept_detection(&tracker,ticket,&src,(StRect){120,90,16,16},ST_PERSON,&now)==ST_INVALID);
    ticket=rearm(src);
    CHECK(st_accept_detection(&tracker,ticket,&src,(StRect){70,32,16,16},ST_PERSON,&now)==ST_OUTSIDE_SELECTION);
    ticket=rearm(src);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,(StKind)0,&now)==ST_INVALID);

    ticket=reset(); /* 两个相同外观：不能仅凭最近点认定主体。 */
    put(current,20,30,0);put(current,44,30,0);now=frame(current,16,1200);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_BIRD,&now)==ST_AMBIGUOUS);
    CHECK(st_get_roi(&tracker,1200,&roi)==ST_LOST);
    ticket=reset();put(current,96,60,0);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_BIRD,&now)==ST_NO_MATCH);
    ticket=reset();memset(source,17,sizeof(source));
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_BIRD,&now)==ST_NO_MATCH);

    /* 连续 40 帧来回移动，人工选点与目标位置始终分离。 */
    ticket=reset();put(current,34,32,0);now=frame(current,16,1200);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_DOG,&now)==ST_OK);
    for(int i=0;i<40;++i) {
        int x=34+(i<20 ? i : 40-i), y=32+i%3;
        memset(current,17,sizeof(current));put(current,x,y,0);
        now=frame(current,17+(uint64_t)i,1233+33*(uint64_t)i);
        CHECK(st_track(&tracker,&now)==ST_OK);
        CHECK(st_get_roi(&tracker,now.time_ms,&roi)==ST_OK && roi.box.x==x && roi.box.y==y);
        CHECK(tracker.manual_x==40 && tracker.manual_y==40 && roi.kind==ST_DOG);
    }
    now=frame(current,100,3000);
    CHECK(st_track(&tracker,&now)==ST_STALE);CHECK(st_get_roi(&tracker,3000,&roi)==ST_LOST);
    StConfig bad={250,80,33,4,0.9,0.08};
    CHECK(st_init(&tracker,W,H,1,bad)==ST_INVALID);

    /* 后台复核期间跟踪继续，慢结果不能将当前位置拉回源帧。 */
    ticket=reset();put(current,36,32,0);now=frame(current,16,1200);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_OK);
    memcpy(source,current,sizeof(source));src=frame(source,16,1200);
    ticket=rearm(src);
    for(int i=1;i<=5;++i) {
        memset(current,17,sizeof(current));put(current,36+3*i,32,0);
        now=frame(current,16+(uint64_t)i,1200+33*(uint64_t)i);
        CHECK(st_track(&tracker,&now)==ST_OK);
        CHECK(st_begin_detection(&tracker,&now,&ignored)==ST_BUSY);
    }
    CHECK(st_accept_detection(&tracker,ticket,&src,(StRect){36,32,16,16},ST_PERSON,&now)==ST_OK);
    CHECK(st_get_roi(&tracker,1365,&roi)==ST_OK && roi.box.x==51 && roi.frame_id==21);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_WRONG_EPOCH);
    memcpy(source,current,sizeof(source));src=now;src.pixels=source;
    ticket=rearm(src);
    CHECK(st_accept_detection(&tracker,ticket,&src,(StRect){51,32,16,16},ST_BIRD,&now)==ST_CLASS_CHANGED);
    CHECK(st_get_roi(&tracker,1365,&roi)==ST_OK && roi.kind==ST_PERSON);
    ticket=rearm(src);
    StFrame old_now=now;old_now.id=20;old_now.time_ms=1332;
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&old_now)==ST_STALE);
    CHECK(st_get_roi(&tracker,1365,&roi)==ST_OK && roi.box.x==51);
    ticket=rearm(src);memset(current,17,sizeof(current));now=frame(current,22,1398);
    CHECK(st_track(&tracker,&now)==ST_NO_MATCH);
    CHECK(st_accept_detection(&tracker,ticket,&src,initial,ST_PERSON,&now)==ST_WRONG_EPOCH);
    CHECK(st_get_roi(&tracker,1398,&roi)==ST_LOST);

    /* 卡住的检测不使请求槽永久占用，新的请求替换过期票据。 */
    ticket=reset();now=frame(current,20,1251);
    CHECK(st_begin_detection(&tracker,&now,&newer)==ST_OK);
    CHECK(st_cancel_detection(&tracker,ticket)==ST_WRONG_EPOCH);
    CHECK(st_cancel_detection(&tracker,newer)==ST_OK);
    bad.search_radius=24;bad.min_similarity=NAN;
    CHECK(st_init(&tracker,W,H,1,bad)==ST_INVALID);
    printf("PASS %u assertions; synthetic grayscale frames; no camera or AI inference\n",checks);
    return 0;
}
