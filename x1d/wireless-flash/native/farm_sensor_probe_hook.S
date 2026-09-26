/* 固定来源：X1D 1.25.0 FARM。仅电脑端候选，没有装载入口。
 * 拟用 B 指令替换 0x214110 的 movw r3,#0x1990。
 * fp 指向原函数保存的返回地址；仅接收电子快门调用及已核对参数。
 */
.syntax unified
.arm
.section .text.farm_sensor_probe_hook,"ax",%progbits
.balign 4
.global farm_sensor_probe_hook
.type farm_sensor_probe_hook,%function
farm_sensor_probe_hook:
    push {r0-r12, lr}
    mrs r12, APSR
    push {r12, lr}

    ldr r0, [fp]
    movw r1, #0x437c
    movt r1, #0x001c
    cmp r0, r1
    bne .Lcontinue_original
    ldrb r0, [fp, #-0x12d]
    cmp r0, #0
    bne .Lcontinue_original
    ldrb r0, [fp, #-0x12e]
    cmp r0, #0
    bne .Lcontinue_original
    ldr r0, [fp, #-0xc]
    cmp r0, #3
    bne .Lcontinue_original

    ldr r0, .Lrecord_address
    bl farm_sensor_probe_after_start

.Lcontinue_original:
    pop {r12, lr}
    msr APSR_nzcvqg, r12
    pop {r0-r12, lr}
    movw r3, #0x1990
    ldr pc, .Lreturn_address
.Lrecord_address:
    .word farm_sensor_probe_record
.Lreturn_address:
    .word 0x00214114
.size farm_sensor_probe_hook, .-farm_sensor_probe_hook

.section .data.farm_sensor_probe_record,"aw",%progbits
.balign 4
.global farm_sensor_probe_record
.type farm_sensor_probe_record,%object
farm_sensor_probe_record:
    .word 0x32504647
    .word 0 /* 默认不准备、不读取硬件。 */
    .zero 80
.size farm_sensor_probe_record, .-farm_sensor_probe_record
.section .note.GNU-stack,"",%progbits
