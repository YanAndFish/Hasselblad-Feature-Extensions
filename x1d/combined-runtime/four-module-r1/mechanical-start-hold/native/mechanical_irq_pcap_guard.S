.syntax unified
.cpu cortex-a9
.arm
.text
.align 2
.global mechanical_irq_reset_call_guard
.type mechanical_irq_reset_call_guard,%function
/* 替换固定原调用点 0x22b910；错误直接使用调用者的原厂返回尾部。
 * 不改变成功时后续取缓存和 DMA 的原指令。
 */
mechanical_irq_reset_call_guard:
    ldr ip,=mechanical_irq_guard_active
    ldr ip,[ip]
    cmp ip,#1
    ldrne pc,=0x22b4fc
    push {r4,lr}
    bl mechanical_irq_bounded_reset
    cmp r0,#0
    pop {r4,lr}
    bxeq lr
    mov r3,#1
    ldr pc,=0x22be3c
.size mechanical_irq_reset_call_guard,.-mechanical_irq_reset_call_guard

.global mechanical_irq_download_call_guard
.type mechanical_irq_download_call_guard,%function
/* 固定调用点 0x22ceb8；下载失败时，资源函数返回失败。
 * 不恢复 PL、GPIO 或资源，不把隔离状态称为已恢复运行。
 */
mechanical_irq_download_call_guard:
    ldr ip,=mechanical_irq_guard_active
    ldr ip,[ip]
    cmp ip,#1
    ldrne pc,=0x22b800
    push {r4,r5,r6,lr}
    ldr r5,=mechanical_irq_download_state
    mov r4,#1
    str r4,[r5]
    ldr r4,=0x22b800
    blx r4
    cmp r0,#0
    moveq r4,#2
    movne r4,#3
    str r4,[r5]
    pop {r4,r5,r6,lr}
    bxeq lr
    mov r3,#1
    ldr pc,=0x22d220
.size mechanical_irq_download_call_guard,.-mechanical_irq_download_call_guard

.global mechanical_irq_ready_branch_guard
.type mechanical_irq_ready_branch_guard,%function
/* 固定分支点 0x22cd90；原函数帧存在，不创造额外调用者帧。 */
mechanical_irq_ready_branch_guard:
    ldr r3,=mechanical_irq_guard_active
    ldr r3,[r3]
    cmp r3,#1
    movwne r3,#0xb2e4
    ldrne pc,=0x22cd94
    push {r4,lr}
    bl mechanical_irq_bounded_ready
    cmp r0,#0
    pop {r4,lr}
    ldreq pc,=0x22cdb4
    mov r3,#1
    ldr pc,=0x22d220
.size mechanical_irq_ready_branch_guard,.-mechanical_irq_ready_branch_guard

.global mechanical_irq_resource_call_guard
.type mechanical_irq_resource_call_guard,%function
/* 普通资源申请不属于专用装载，原样转交，禁止改变其错误/唤醒语义。
 * 专用任务直接调用 0x22cc4c，不经过本调用点。 */
mechanical_irq_resource_call_guard:
    ldr pc,=0x22cc4c
.size mechanical_irq_resource_call_guard,.-mechanical_irq_resource_call_guard
