/* 固定版本、两处入口；仅电脑端候选。原厂控制写与定时顺序保留。 */
.syntax unified
.arm
.macro SAVE
    push {r0-r12, lr}
    mrs r12, APSR
    push {r12, lr}
.endm
.macro RESTORE
    pop {r12, lr}
    msr APSR_nzcvqg, r12
    pop {r0-r12, lr}
.endm
.macro ES_GUARD fail
    ldr r0, [fp]
    movw r1, #0x437c
    movt r1, #0x001c
    cmp r0, r1
    bne \fail
    ldrb r0, [fp, #-0x12d]
    cmp r0, #0
    bne \fail
    ldrb r0, [fp, #-0x12e]
    cmp r0, #0
    bne \fail
.endm

.section .text.farm_sync_clear_hook,"ax",%progbits
.balign 4
.global farm_sync_clear_hook
.type farm_sync_clear_hook,%function
farm_sync_clear_hook:
    /* 0x21409c 原 BL，候选仍以 BL 进入，LR=0x2140a0。 */
    SAVE
    ES_GUARD .Lbefore_return
    ldr r0, .Lclear_record
    bl farm_sync_begin
    str r0, [sp, #12] /* 仅替换传入原厂写入函数的 r1。 */
.Lbefore_return:
    RESTORE
    push {r12, lr}
    ldr r12, .Loriginal_write
    blx r12
    pop {r12, lr}
    SAVE
    ES_GUARD .Lafter_return
    ldr r0, .Lclear_record
    bl farm_sync_cleared
.Lafter_return:
    RESTORE
    bx lr
.Lclear_record: .word farm_sync_record
.Loriginal_write: .word 0x00238820
.size farm_sync_clear_hook, .-farm_sync_clear_hook

.section .text.farm_sync_observe_hook,"ax",%progbits
.balign 4
.global farm_sync_observe_hook
.type farm_sync_observe_hook,%function
farm_sync_observe_hook:
    /* 0x1c4380，只在原厂 ES 函数内部，0x1c7fdc 已正常返回。 */
    SAVE
    ldr r0, .Lobserve_record
    ldr r1, [fp, #-0x74]
    ldr r2, [fp, #-0x70]
    bl farm_sync_observe
    RESTORE
    movw r3, #0x1690
    ldr pc, .Lobserve_continue
.Lobserve_record: .word farm_sync_record
.Lobserve_continue: .word 0x001c4384
.size farm_sync_observe_hook, .-farm_sync_observe_hook

.section .text.farm_sync_progress_hook,"ax",%progbits
.balign 4
.global farm_sync_progress_hook
.type farm_sync_progress_hook,%function
farm_sync_progress_hook:
    /* 0x1c4458，r0 为原厂 0x214520 的返回值。 */
    SAVE
    mov r1, r0
    ldr r0, .Lprogress_record
    bl farm_sync_progress
    RESTORE
    mov r3, r0
    ldr pc, .Lprogress_continue
.Lprogress_record: .word farm_sync_record
.Lprogress_continue: .word 0x001c445c
.size farm_sync_progress_hook, .-farm_sync_progress_hook

.section .text.farm_sync_stop_hook,"ax",%progbits
.balign 4
.global farm_sync_stop_hook
.type farm_sync_stop_hook,%function
farm_sync_stop_hook:
    /* 0x1c44f4 正常路径；超时调用 0x1c4444 不经过这里。 */
    SAVE
    ldr r0, .Lstop_record
    bl farm_sync_stop
    RESTORE
    mov r0, #1
    ldr pc, .Lstop_continue
.Lstop_record: .word farm_sync_record
.Lstop_continue: .word 0x001c44f8
.size farm_sync_stop_hook, .-farm_sync_stop_hook

.section .data.farm_sync_record,"aw",%progbits
.balign 4
.global farm_sync_record
.type farm_sync_record,%object
farm_sync_record:
    .word 0x33534647
    .zero 352
.size farm_sync_record, .-farm_sync_record
.section .note.GNU-stack,"",%progbits
