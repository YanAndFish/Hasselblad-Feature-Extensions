/* 第七条调用路径观察。保留原 BL 的返回地址；无 MMIO、时钟或外设访问。
 * 事件仅表明代码到达，不是物理闪光/积分时刻。记录区最多 16 项。
 */
.syntax unified
.arm
.macro WRAPPER name, stage, target
.section .text.\name,"ax",%progbits
.balign 4
.global \name
.type \name,%function
\name:
    push {r0-r12, lr}
    mrs r12, APSR
    push {r12, lr}
    mov r2, r0
    mov r1, #\stage
    ldr r0, 1f
    bl route7_append
    pop {r12, lr}
    msr APSR_nzcvqg, r12
    pop {r0-r12, lr}
    ldr pc, 2f
1:  .word route7_record
2:  .word \target
.size \name, .-\name
.endm
WRAPPER route7_normal, 1, 0x001c3810
WRAPPER route7_entry, 2, 0x001c818c
/* 位于脉冲拉低前，脉冲两沿之间不插入观察代码。 */
WRAPPER route7_pulse, 3, 0x0023899c
/* sensor 调用与原等待已返回，不能用此事件解释实际积分起点。 */
WRAPPER route7_after_sensor, 4, 0x001c7fdc

.section .text.route7_append,"ax",%progbits
.balign 4
.type route7_append,%function
route7_append:
    ldr r3, [r0]
    movw r12, #0x3747
    movt r12, #0x3152
    cmp r3, r12
    bxne lr
    ldr r3, [r0, #4]
    cmp r3, #1
    bxne lr
    add r12, r0, #24
    ldrex r3, [r12]
    cmp r3, #0
    bne .Llost
    mov r3, #1
    strex r4, r3, [r12]
    cmp r4, #0
    bne .Llost
    dmb ish
    ldr r3, [r0, #4]
    cmp r3, #1
    bne .Lunlock
    ldr r3, [r0, #8]
    tst r3, #1
    bne .Lcorrupt
    add r3, r3, #1
    str r3, [r0, #8]
    dmb ish
    ldr r4, [r0, #12]
    cmp r4, #16
    bhs .Lfull
    cmp r1, #2
    ldrbeq r2, [r2, #4]
    movne r2, #255
    orr r1, r1, r2, lsl #8
    add r2, r0, #32
    str r1, [r2, r4, lsl #2]
    add r4, r4, #1
    str r4, [r0, #12]
    b .Lcommit
.Lfull:
    mov r4, #1
    str r4, [r0, #16]
.Lcommit:
    dmb ish
    add r3, r3, #1
    str r3, [r0, #8]
.Lunlock:
    dmb ish
    mov r3, #0
    str r3, [r0, #24]
    bx lr
.Lcorrupt:
    mov r3, #1
    str r3, [r0, #20]
    b .Lunlock
.Llost:
    clrex
    mov r3, #1
    str r3, [r0, #20]
    bx lr
.size route7_append, .-route7_append

.section .data.route7_record,"aw",%progbits
.balign 4
.global route7_record
.type route7_record,%object
route7_record:
    .word 0x31523747
    .zero 92
.size route7_record, .-route7_record
.section .note.GNU-stack,"",%progbits
