/* SPDX-License-Identifier: MIT
 * Copyright (c) 2026 Hasselblad Feature Extensions contributors
 */
#include "target_exchange.h"
#include <stddef.h>

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error The reviewed X1D II exchange format is little-endian
#endif
_Static_assert(sizeof(EafTargetExchange)==112,"Target and observation packet layout");
_Static_assert(offsetof(EafTargetExchange,bound_pid)==48,"Binding observations are separate");
_Static_assert(offsetof(EafTargetExchange,observation)==56,"Independent writer region");

void eaf_target_init(EafTargetExchange *p)
{
    *p=(EafTargetExchange){.magic=EAF_TARGET_MAGIC,.version=EAF_TARGET_VERSION};
}

int eaf_target_publish(EafTargetExchange *p,enum EafMode mode,
                        uint32_t current_generation,const EafTargetSnapshot *target)
{
    uint32_t seq=__atomic_load_n(&p->sequence,__ATOMIC_RELAXED);
    if (p->magic!=EAF_TARGET_MAGIC || p->version!=EAF_TARGET_VERSION ||
        (seq&1) || mode<EAF_ORDINARY || mode>EAF_EYE) return 0;
    /* Paired with the reader's acquire fence: observing any new payload must
     * also make the preceding odd marker visible to the final sequence read.
     */
    __atomic_store_n(&p->sequence,seq+1,__ATOMIC_RELAXED);
    __atomic_thread_fence(__ATOMIC_RELEASE);
    uint64_t received=target?target->received_ns:0;
    uint32_t flags=target ? (!!target->geometry_confirmed |
        (!!target->face_usable<<1) | (!!target->eye_usable<<2)) : 0;
#define PUT(field,value) __atomic_store_n(&p->field,(value),__ATOMIC_RELAXED)
    PUT(mode,(uint32_t)mode);
    PUT(current_generation,current_generation);
    PUT(received_lo,(uint32_t)received);
    PUT(received_hi,(uint32_t)(received>>32));
    PUT(target_generation,target?target->preview_generation:0);
    PUT(face_count,target?target->face_count:0);
    PUT(face_point,target?target->face_point:0);
    PUT(eye_point,target?target->eye_point:0);
    PUT(qualification,flags);
#undef PUT
    __atomic_store_n(&p->sequence,seq+2,__ATOMIC_RELEASE);
    return 1;
}

int eaf_target_read(const EafTargetExchange *p,EafTriggerSnapshot *out)
{
    if (p->magic!=EAF_TARGET_MAGIC || p->version!=EAF_TARGET_VERSION) return 0;
    uint32_t seq=__atomic_load_n(&p->sequence,__ATOMIC_ACQUIRE);
    if (seq&1) return 0;
#define GET(field) __atomic_load_n(&p->field,__ATOMIC_RELAXED)
    uint32_t mode=GET(mode),generation=GET(current_generation);
    uint32_t lo=GET(received_lo),hi=GET(received_hi);
    EafTargetSnapshot target={.received_ns=(uint64_t)lo|((uint64_t)hi<<32),
        .preview_generation=GET(target_generation),.face_count=GET(face_count),
        .face_point=GET(face_point),.eye_point=GET(eye_point)};
    uint32_t flags=GET(qualification);
#undef GET
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if (__atomic_load_n(&p->sequence,__ATOMIC_RELAXED)!=seq ||
        mode>EAF_EYE || (flags&~7u)) return 0;
    target.geometry_confirmed=flags&1u;
    target.face_usable=(flags>>1)&1u;
    target.eye_usable=(flags>>2)&1u;
    *out=(EafTriggerSnapshot){.mode=(enum EafMode)mode,
        .preview_generation=generation,.target=target};
    return 1;
}

int eaf_observation_publish(EafTargetExchange *p,uint32_t user_point,
                            const EafRequest *r,int timeout,
                            const EafTriggerSnapshot *s,void *watcher)
{
    EafRequestObservation *o=&p->observation;
    uint32_t seq=__atomic_load_n(&o->sequence,__ATOMIC_RELAXED);
    if(p->magic!=EAF_TARGET_MAGIC || p->version!=EAF_TARGET_VERSION || (seq&1)) return 0;
    uint32_t count=__atomic_load_n(&o->dispatch_count,__ATOMIC_RELAXED)+1;
    __atomic_store_n(&o->sequence,seq+1,__ATOMIC_RELAXED);
    __atomic_thread_fence(__ATOMIC_RELEASE);
#define PUT(field,value) __atomic_store_n(&o->field,(value),__ATOMIC_RELAXED)
    PUT(dispatch_count,count);PUT(user_point,user_point);PUT(point,r->point);
    PUT(size,r->size);PUT(timeout,(uint32_t)timeout);PUT(kind,(uint32_t)r->kind);
    PUT(reason,(uint32_t)r->reason);PUT(watcher_nonnull,watcher!=0);
    PUT(generation,s->preview_generation);PUT(received_lo,(uint32_t)s->target.received_ns);
    PUT(received_hi,(uint32_t)(s->target.received_ns>>32));
    PUT(decision_lo,(uint32_t)s->now_ns);PUT(decision_hi,(uint32_t)(s->now_ns>>32));
#undef PUT
    __atomic_store_n(&o->sequence,seq+2,__ATOMIC_RELEASE);
    return 1;
}

int eaf_observation_read(const EafTargetExchange *p,EafRequestObservation *out)
{
    const EafRequestObservation *o=&p->observation;
    if(p->magic!=EAF_TARGET_MAGIC || p->version!=EAF_TARGET_VERSION) return 0;
    uint32_t seq=__atomic_load_n(&o->sequence,__ATOMIC_ACQUIRE);
    if(seq&1) return 0;
#define GET(field) .field=__atomic_load_n(&o->field,__ATOMIC_RELAXED)
    EafRequestObservation copy={.sequence=seq,GET(dispatch_count),GET(user_point),
        GET(point),GET(size),GET(timeout),GET(kind),GET(reason),GET(watcher_nonnull),
        GET(generation),GET(received_lo),GET(received_hi),GET(decision_lo),GET(decision_hi)};
#undef GET
    __atomic_thread_fence(__ATOMIC_ACQUIRE);
    if(__atomic_load_n(&o->sequence,__ATOMIC_RELAXED)!=seq) return 0;
    *out=copy;
    return 1;
}
