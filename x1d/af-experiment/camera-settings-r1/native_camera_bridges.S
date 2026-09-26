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
bridge na_direction_bridge,na_direction
bridge na_probe_bridge,na_probe_speed
bridge na_fast_bridge,na_fast_speed
bridge na_fine_bridge,na_fine_speed
bridge na_reset_bridge,na_cycle_reset
bridge as_receive_bridge,as_receive
bridge as_near_limit_bridge,as_near_limit
.balign 4
.global as_native_near
.type as_native_near,%function
as_native_near:
 push {fp,lr}
 ldr pc,1f
1: .word 0x1a049c
.size as_native_near,.-as_native_near
