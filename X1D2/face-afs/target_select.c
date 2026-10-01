/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#include "target_select.h"

static int in_box(const EafRawFace *f,int x,int y)
{
    return x>=f->x && x<f->x+f->width && y>=f->y && y<f->y+f->height;
}

EafTargetSnapshot eaf_select_target(const EafRawFace *faces,uint32_t count,
                                   uint64_t received_ns,uint32_t generation,
                                   unsigned geometry_approved,unsigned eye_index)
{
    EafTargetSnapshot t={.received_ns=received_ns,.preview_generation=generation,
                         .geometry_confirmed=!!geometry_approved};
    if(count>512 || (count && !faces)) return t;
    const EafRawFace *selected=0;
    for(uint32_t i=0;i<count;++i) {
        const EafRawFace *f=faces+i;
        if(f->score<60 || f->score>100 || f->x<0 || f->y<0 ||
           f->width<16 || f->height<18 || f->width>160 || f->height>120 ||
           f->x>160-f->width || f->y>120-f->height) continue;
        selected=f;++t.face_count;
    }
    t.face_usable=t.face_count!=0;
    if(t.face_count!=1) return t;
    const EafRawFace *f=selected;
    if(!eaf_pack_preview_point(160,120,2*f->x+f->width,2*f->y+f->height,&t.face_point))
        { t.face_usable=0;return t; }
    if(eye_index>1 || f->score<80 || f->height<40) return t;
    for(unsigned k=0;k<5;++k)
        if(!in_box(f,f->landmarks[2*k],f->landmarks[2*k+1])) return t;
    int lx=f->landmarks[0],ly=f->landmarks[1];
    int rx=f->landmarks[2],ry=f->landmarks[3];
    int dx=rx-lx,dy=ly>ry?ly-ry:ry-ly;
    int nx=f->landmarks[4],ny=f->landmarks[5];
    int lower_eye=ly>ry?ly:ry;
    if(dx<12 || 3*dy>dx || lower_eye>f->y+3*f->height/5 ||
       nx<lx || nx>rx || ny<=lower_eye ||
       2*ny>=f->landmarks[7]+f->landmarks[9]) return t;
    t.eye_usable=eaf_pack_preview_point(160,120,2*f->landmarks[2*eye_index],
                                       2*f->landmarks[2*eye_index+1],&t.eye_point);
    return t;
}
