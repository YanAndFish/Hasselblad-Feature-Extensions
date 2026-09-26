.syntax unified
.arm
.section .text.camera_bridges,"ax",%progbits
.macro bridge name,target
.balign 4
.global \name
.type \name,%function
\name:
 ldr ip, [pc, #0]
 bx ip
 .word \target
.size \name, .-\name
.endm
#ifdef AF_PROFILE_TEST
bridge na_direction_bridge,na_direction
#endif
bridge na_probe_bridge,na_probe_speed
bridge na_fast_bridge,na_fast_speed
bridge na_fine_bridge,na_fine_speed
bridge na_reset_bridge,na_cycle_reset
#ifdef AF_PROFILE_TEST
bridge as_receive_bridge,as_receive
#endif
bridge as_near_limit_bridge,as_near_limit
bridge af_peak_bridge,af_peak_window
.balign 4
.global af_native_peak
.type af_native_peak,%function
af_native_peak:
 push {fp,lr}
 ldr pc,1f
1: .word 0x19d5cc
.size af_native_peak,.-af_native_peak
.balign 4
.global as_native_near
.type as_native_near,%function
as_native_near:
 push {fp,lr}
 ldr pc,1f
1: .word 0x1a049c
.size as_native_near,.-as_native_near

.balign 4
.global na_direction_tail
.type na_direction_tail,%function
na_direction_tail:
 push {r0-r3,r12,lr}
 ldr ip,=na_after_direction
 blx ip
 pop {r0-r3,r12,lr}
 sub sp,fp,#8
 pop {r4,fp,pc}
.size na_direction_tail,.-na_direction_tail
.ltorg

/* Both replaced instructions are STRB: preserve every register and flags. */
.macro identity_observer name,target,resume,publish
.balign 4
.global \name
.type \name,%function
\name:
 strb r2,[r3]
 push {r0-r3,r12,lr}
 mrs r0,cpsr
 push {r0,r1}
 .if \publish
 ldrb r0,[fp,#-0x2a5]
 ldrb r1,[fp,#-0x2a6]
 ldrb r2,[fp,#-5]
 .endif
 ldr ip,=\target
 blx ip
 pop {r0,r1}
 msr cpsr_f,r0
 pop {r0-r3,r12,lr}
 ldr pc,=\resume
.size \name,.-\name
.endm
identity_observer af_identity_invalid_bridge,af_identity_invalidate,0x198910,0
identity_observer af_identity_publish_bridge,af_identity_publish,0x1990fc,1
.ltorg
