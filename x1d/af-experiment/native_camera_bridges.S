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
