#include "af_policy.h"
#include "native_config.h"
/* Test-only manual policy. Generic-slot matching is not an eight-lens identity proof. */
u32 af_policy_begin(struct AfPolicy *p,u32 generation){
    u32 status=na_config_latch(generation);const struct NaConfig *c=&na_config_bank.active;
    u32 reported=c->start_speed==AP_DYNAMIC_70?af_reported_start_speed():0;
    *p=(struct AfPolicy){.eligible=!status,.start_speed=c->start_speed,.start_samples=c->start_samples,
        .probe=c->probe,.fast=c->fast,.fine=c->fine,.far_first=(c->flags&NA_FAR_FIRST)!=0,
        .fine_advance_ms=c->fine_advance_ms<65534?c->fine_advance_ms:0,.reported_speed=reported};return status;
}
int af_policy_current(const struct AfPolicy *p){return p->eligible && *(volatile unsigned char *)0x2adc79==18 &&
    (p->start_speed!=AP_DYNAMIC_70 || (p->reported_speed && af_reported_start_speed()==p->reported_speed));}
/* Test harness comparison only. Neither profile patches the factory direction call. */
float na_direction(unsigned int *maximum){return ((float (*)(unsigned int *))0x19e47c)(maximum);}
