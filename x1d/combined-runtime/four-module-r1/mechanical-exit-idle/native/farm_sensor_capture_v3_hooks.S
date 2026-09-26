/* 仅电脑端验证。两处原厂指令必须分别保存、校验和恢复。
 * 不得在旧 GFP2 代码仍驻留时原位覆盖，也没有装载入口。
 */
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

.section .text.farm_capture_encoding_hook,"ax",%progbits
.balign 4
.global farm_capture_encoding_hook
.type farm_capture_encoding_hook,%function
farm_capture_encoding_hook:
    SAVE
    /* 0x233c7c：原编码函数返回前；[fp] 是其保存的调用者返回地址。 */
    ldr r0, [fp]
    movw r1, #0x0674
    movt r1, #0x0023
    cmp r0, r1
    bne .Lencoded_return
    ldr r0, [fp, #-0x30]
    movw r1, #0x1690
    movt r1, #0x006c
    cmp r0, r1
    bne .Lencoded_return
    ldr r0, [fp, #-0x34]
    movw r1, #0xb2e8
    movt r1, #0x006d
    cmp r0, r1
    bne .Lencoded_return
    /* SAVE 之后的原 r0/r1 是原编码函数返回的输入曝光微秒数。 */
    ldr r1, [sp, #8]
    ldr r2, [sp, #12]
    ldr r0, .Lencoding_record
    bl farm_capture_encoding
.Lencoded_return:
    RESTORE
    sub sp, fp, #8
    ldr pc, .Lencoding_continue
.Lencoding_record:
    .word farm_capture_record
.Lencoding_continue:
    .word 0x00233c80
.size farm_capture_encoding_hook, .-farm_capture_encoding_hook

.section .text.farm_capture_start_hook,"ax",%progbits
.balign 4
.global farm_capture_start_hook
.type farm_capture_start_hook,%function
farm_capture_start_hook:
    SAVE
    ldr r0, [fp]
    movw r1, #0x437c
    movt r1, #0x001c
    cmp r0, r1
    bne .Lstart_return
    ldrb r0, [fp, #-0x12d]
    cmp r0, #0
    bne .Lstart_return
    ldrb r0, [fp, #-0x12e]
    cmp r0, #0
    bne .Lstart_return
    ldr r0, [fp, #-0xc]
    cmp r0, #3
    bne .Lstart_return
    ldr r0, .Lstart_record
    bl farm_capture_start
.Lstart_return:
    RESTORE
    movw r3, #0x1990
    ldr pc, .Lstart_continue
.Lstart_record:
    .word farm_capture_record
.Lstart_continue:
    .word 0x00214114
.size farm_capture_start_hook, .-farm_capture_start_hook

.section .data.farm_capture_record,"aw",%progbits
.balign 4
.global farm_capture_record
.type farm_capture_record,%object
farm_capture_record:
    .word 0x33504647
    .word 0
    .zero 108
.size farm_capture_record, .-farm_capture_record
.section .note.GNU-stack,"",%progbits
