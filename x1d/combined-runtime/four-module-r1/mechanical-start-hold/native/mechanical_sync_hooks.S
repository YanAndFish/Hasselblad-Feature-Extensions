.syntax unified
.arm
.macro SAVE
    push {r0-r12,lr}
    mrs r12,APSR
    push {r12,lr}
.endm
.macro RESTORE
    pop {r12,lr}
    msr APSR_nzcvqg,r12
    pop {r0-r12,lr}
.endm
/* 固定调用链：2a/21d -> 1c4eac(source=3,mode=0/1) -> 213fcc(cmd=0)。 */
.macro MECH_GUARD fail
    ldr r0,[fp]
    movw r1,#0x5244
    movt r1,#0x001c
    cmp r0,r1
    bne \fail
    ldrb r0,[fp,#-0x12d]
    cmp r0,#0
    bne \fail
    ldrb r1,[fp,#-0x12e]
    cmp r1,#1
    bhi \fail
    ldr r2,[fp,#-4]
    add r3,fp,#0x160
    cmp r2,r3
    bne \fail
    ldrb r0,[r2,#-0x14d]
    cmp r0,#3
    bne \fail
    ldrb r0,[r2,#-0x14e]
    cmp r0,r1
    bne \fail
    ldr r0,[r2]
    movw r3,#0xe080
    movt r3,#0x001c
    cmp r1,#1
    addeq r3,r3,#0x1c
    cmp r0,r3
    bne \fail
.endm
.section .text.mechanical_sync_clear_hook,"ax",%progbits
.balign 4
.global mechanical_sync_clear_hook
.type mechanical_sync_clear_hook,%function
mechanical_sync_clear_hook:
    SAVE
    ldr r0,.Lrecord_clear
    bl mechanical_sync_cancel_old
    MECH_GUARD .Lbefore_done
    ldr r0,.Lrecord_clear
    bl mechanical_sync_begin
    str r0,[sp,#12]
.Lbefore_done:
    RESTORE
    push {r4,lr}
    ldr r4,.Lwrite_clear
    blx r4
    pop {r4,lr}
    SAVE
    MECH_GUARD .Lafter_done
    ldr r0,.Lrecord_clear
    bl mechanical_sync_cleared
.Lafter_done:
    RESTORE
    bx lr
.Lrecord_clear: .word mechanical_sync_record
.Lwrite_clear: .word 0x238820
.size mechanical_sync_clear_hook,.-mechanical_sync_clear_hook
.section .text.mechanical_sync_start_hook,"ax",%progbits
.balign 4
.global mechanical_sync_start_hook
.type mechanical_sync_start_hook,%function
mechanical_sync_start_hook:
    push {r4,lr}
    ldr r4,.Lwrite_start
    blx r4
    pop {r4,lr}
    SAVE
    MECH_GUARD .Lstart_done
    ldr r0,.Lrecord_start
    bl mechanical_sync_observe
.Lstart_done:
    RESTORE
    bx lr
.Lrecord_start: .word mechanical_sync_record
.Lwrite_start: .word 0x238820
.size mechanical_sync_start_hook,.-mechanical_sync_start_hook
/* 原厂已经读取状态，复用 r0，不增加读取、等待或改变停止策略。 */
.macro STATUS_HOOK name,final
.section .text.\name,"ax",%progbits
.balign 4
.global \name
.type \name,%function
\name:
    push {r4,lr}
    ldr r4,1f
    blx r4
    pop {r4,lr}
    SAVE
    mov r1,r0
    ldr r0,2f
    mov r2,#\final
    bl mechanical_sync_sample
    RESTORE
    bx lr
1: .word 0x23899c
2: .word mechanical_sync_record
.size \name,.-\name
.endm
STATUS_HOOK mechanical_sync_status_hook,0
STATUS_HOOK mechanical_sync_finish_hook,1
.section .data.mechanical_sync_record,"aw",%progbits
.balign 4
.global mechanical_sync_record
.type mechanical_sync_record,%object
mechanical_sync_record:
    .word 0x31534d47
    .zero 360
.size mechanical_sync_record,.-mechanical_sync_record
.section .note.GNU-stack,"",%progbits
