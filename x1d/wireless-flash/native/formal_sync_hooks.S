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
.macro ES_GUARD fail
    ldr r0,[fp]
    movw r1,#0x437c
    movt r1,#0x001c
    cmp r0,r1
    bne \fail
    ldrb r0,[fp,#-0x12d]
    cmp r0,#0
    bne \fail
    ldrb r0,[fp,#-0x12e]
    cmp r0,#0
    bne \fail
.endm
/* 两类原厂调用经过同一个清旧位入口；原厂写入只调用一次。 */
.section .text.formal_sync_clear_hook,"ax",%progbits
.balign 4
.global formal_sync_clear_hook
.type formal_sync_clear_hook,%function
formal_sync_clear_hook:
    SAVE
    ldr r0,.Lrecord_clear
    bl formal_sync_cancel
    MECH_GUARD .Ltry_es
    mov r2,r1
    mov r1,#0
    b .Lbegin
.Ltry_es:
    ES_GUARD .Lbefore_done
    mov r1,#1
    mov r2,#0
.Lbegin:
    ldr r0,.Lrecord_clear
    bl formal_sync_begin
    str r0,[sp,#12]
.Lbefore_done:
    RESTORE
    push {r4,lr}
    ldr r4,.Lwrite_clear
    blx r4
    pop {r4,lr}
    SAVE
    /* 前段已判别并建stage=1；不重复运行两个独立包装。 */
    ldr r0,.Lrecord_clear
    bl formal_sync_cleared
    RESTORE
    bx lr
.Lrecord_clear: .word formal_sync_record
.Lwrite_clear: .word 0x238820
.size formal_sync_clear_hook,.-formal_sync_clear_hook
.section .text.formal_sync_start_hook,"ax",%progbits
.balign 4
.global formal_sync_start_hook
.type formal_sync_start_hook,%function
formal_sync_start_hook:
    push {r4,lr}
    ldr r4,.Lwrite_start
    blx r4
    pop {r4,lr}
    SAVE
    MECH_GUARD .Lstart_done
    ldr r0,.Lrecord_start
    bl formal_sync_started
.Lstart_done:
    RESTORE
    bx lr
.Lrecord_start: .word formal_sync_record
.Lwrite_start: .word 0x238820
.size formal_sync_start_hook,.-formal_sync_start_hook
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
    bl formal_sync_mechanical
    RESTORE
    bx lr
1: .word 0x23899c
2: .word formal_sync_record
.size \name,.-\name
.endm
STATUS_HOOK formal_sync_status_hook,0
STATUS_HOOK formal_sync_finish_hook,1
.section .text.formal_sync_observe_hook,"ax",%progbits
.balign 4
.global formal_sync_observe_hook
.type formal_sync_observe_hook,%function
formal_sync_observe_hook:
    SAVE
    ldr r0,.Lobserve_record
    ldr r1,[fp,#-0x74]
    ldr r2,[fp,#-0x70]
    bl formal_sync_es_observe
    RESTORE
    movw r3,#0x1690
    ldr pc,.Lobserve_continue
.Lobserve_record: .word formal_sync_record
.Lobserve_continue: .word 0x1c4384
.size formal_sync_observe_hook,.-formal_sync_observe_hook
.section .text.formal_sync_progress_hook,"ax",%progbits
.balign 4
.global formal_sync_progress_hook
.type formal_sync_progress_hook,%function
formal_sync_progress_hook:
    SAVE
    mov r1,r0
    ldr r0,.Lprogress_record
    bl formal_sync_es_progress
    RESTORE
    mov r3,r0
    ldr pc,.Lprogress_continue
.Lprogress_record: .word formal_sync_record
.Lprogress_continue: .word 0x1c445c
.size formal_sync_progress_hook,.-formal_sync_progress_hook
.section .text.formal_sync_stop_hook,"ax",%progbits
.balign 4
.global formal_sync_stop_hook
.type formal_sync_stop_hook,%function
formal_sync_stop_hook:
    SAVE
    ldr r0,.Lstop_record
    bl formal_sync_es_stop
    RESTORE
    mov r0,#1
    ldr pc,.Lstop_continue
.Lstop_record: .word formal_sync_record
.Lstop_continue: .word 0x1c44f8
.size formal_sync_stop_hook,.-formal_sync_stop_hook
.section .data.formal_sync_record,"aw",%progbits
.balign 4
.global formal_sync_record
.type formal_sync_record,%object
formal_sync_record:
    .word 0x31534648
    .zero 360
.size formal_sync_record,.-formal_sync_record
.section .note.GNU-stack,"",%progbits
