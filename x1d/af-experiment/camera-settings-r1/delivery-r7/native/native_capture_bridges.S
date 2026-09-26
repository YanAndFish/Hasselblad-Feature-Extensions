.syntax unified
.arm
.section .text.capture_bridges,"ax",%progbits
.macro SAVE
 push {r0-r3,r12,lr}
 mrs r12,apsr
 push {r12,lr}
.endm
.macro RESTORE
 pop {r12,lr}
 msr APSR_nzcvq,r12
 pop {r0-r3,r12,lr}
.endm
#ifdef AF_PROFILE_TEST
.global nc_raw_entry
.type nc_raw_entry,%function
nc_raw_entry:
 SAVE
 ldr r0,[fp,#-0x10]
 ldr r1,[fp,#-0x14]
 ldrb r2,[fp,#-0x19]
 bl nc_raw
 RESTORE
 ldrb r3,[fp,#-0x19]
 ldr pc,=0x1f0d30
.size nc_raw_entry,.-nc_raw_entry
.global nc_cv_entry
.type nc_cv_entry,%function
nc_cv_entry:
 str r1,[r3,r2,lsl #2]
 SAVE
 mov r0,r1
 mov r1,r2
 bl nc_cv_fifo
 RESTORE
 ldr pc,=0x1a1b4c
.size nc_cv_entry,.-nc_cv_entry
.global nc_position_entry
.type nc_position_entry,%function
nc_position_entry:
 strh r2,[r3]
 SAVE
 sxth r0,r2
 ldr r1,[fp,#-0x28]
 ldrb r2,[fp,#-0x23]
 bl nc_position_fifo
 RESTORE
 ldr pc,=0x1a2134
.size nc_position_entry,.-nc_position_entry
#endif
.global nc_accepted_entry
.type nc_accepted_entry,%function
nc_accepted_entry:
 strh r2,[r3]
 SAVE
 mov r0,r2
 bl nc_accepted
 RESTORE
 ldr pc,=0x1a306c
.size nc_accepted_entry,.-nc_accepted_entry
.macro VENEER name,target
 .global \name
 .type \name,%function
 \name:
 ldr ip,[pc,#0]
 bx ip
 .word \target
 .size \name,.-\name
.endm
VENEER nc_reset_bridge,nc_cycle_reset
VENEER nc_probe_bridge,nc_probe_speed
VENEER nc_fast_bridge,nc_fast_speed
VENEER nc_fine_bridge,nc_fine_speed
.ltorg
