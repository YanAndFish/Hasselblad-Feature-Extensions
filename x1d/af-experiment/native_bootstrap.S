.syntax unified
.arm
.section .text.bootstrap,"ax",%progbits
.global nr_idle_gate
.type nr_idle_gate,%function
nr_idle_gate:
 push {r0-r3,r12,lr}
 mrs r2,apsr
 push {r2,r3}
 ldr r0,=0x6bb46c
 ldrb r1,[r0]
 cmp r1,#0
 bne .Lnative
 ldr r0,=nr_request
 bl nr_reserve
 ldr r0,=nr_gate_control
 ldr r1,[r0]
 cmp r1,#2
 beq .Lnative
 ldr r1,[r0,#4]
 add r1,r1,#1
 str r1,[r0,#4]
 dmb sy
 pop {r2,r3}
 msr APSR_nzcvq,r2
 pop {r0-r3,r12,lr}
 ldr pc,=0x19d198
.Lnative:
 pop {r2,r3}
 msr APSR_nzcvq,r2
 pop {r0-r3,r12,lr}
 ldr r3,[fp,#-0x94]
 ldr pc,=0x19b964
.size nr_idle_gate,.-nr_idle_gate

.global nr_wake
.type nr_wake,%function
nr_wake:
 push {r0,lr}
 ldr r1,[r0,#4]
 ldr r2,=nr_gate_control+4
 cmp r1,r2
 bne .Lread
 ldr r1,[r2,#4]
 cmp r1,#0
 bne .Lread
 ldr r1,=0x6bb46c
 ldrb r1,[r1]
 cmp r1,#0
 bne .Lread
 mov r1,#1
 str r1,[r2,#4]
 dmb sy
 mov r0,#16
 ldr r12,=0x1a4890
 blx r12
.Lread:
 pop {r0,lr}
 ldr pc,=0x1e1768
.size nr_wake,.-nr_wake
.ltorg

.section .data.bootstrap,"aw",%progbits
.balign 32
.global nr_request
.type nr_request,%object
nr_request:
 .word 0x31524e41,1,1,16384,131072
 .word 0x31524e41 ^ 1 ^ 1 ^ 16384 ^ 131072 ^ 0x6c871ae5
 .word 1,0,0,0,0,0,0
.size nr_request,.-nr_request
.balign 4
.global nr_gate_control
.type nr_gate_control,%object
nr_gate_control:
 .word 0,0,0
.size nr_gate_control,.-nr_gate_control
