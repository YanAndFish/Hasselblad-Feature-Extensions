// Runs only inside our separate image-preview process, on its Qt event thread.
// Replaces its timeout functor; no camera-service/main GUI instructions change.
.text
#ifndef RESIDENT_INTERVAL_MS
#define RESIDENT_INTERVAL_MS 20
#endif
.global resident_start
.global resident_mailbox
resident_start:
    stp x29, x30, [sp, #-48]!
    mov x29, sp
    stp x19, x20, [sp, #16]
    stp x21, x22, [sp, #32]
    adr x19, resident_start
    ldr x16, =0xad76c8
    sub x19, x19, x16
    cmp w0, #1
    b.eq tick
    cbnz w0, done
    cbz x1, done
    mov x0, x1
    ldr x16, =0x219498
    add x16, x19, x16
    blr x16
    b done
tick:
    adr x21, resident_mailbox
    ldrb w22, [x21]
    cmp w22, #2
    b.eq quit
    cmp w22, #1
    b.hi schedule
    ldr x16, =0x21cf850
    add x16, x19, x16
    ldr x8, [x16, #16]
    cmp x8, #1
    b.ne schedule
    ldr x8, [x16, #8]
    cbz x8, schedule
    ldr x20, [x8]
    cbz x20, schedule
    mov x0, x20
    ldr x16, =0xb45a70
    add x16, x19, x16
    blr x16
    cmp w0, w22
    b.eq schedule
    mov x0, x20
    mov w1, w22
    ldr x16, =0xb45400
    add x16, x19, x16
    blr x16
schedule:
    mov w0, #24
    ldr x16, =0x2194e8
    add x16, x19, x16
    blr x16
    cbz x0, quit
    mov w8, #1
    str x8, [x0]
    adr x8, resident_start
    str x8, [x0, #8]
    str xzr, [x0, #16]
    mov x3, x0
    mov w0, #RESIDENT_INTERVAL_MS
    mov w1, #0
    mov x2, xzr
    ldr x16, =0x901ea8
    add x16, x19, x16
    blr x16
    b done
quit:
    mov w0, #0
    ldr x16, =0x8c2410
    add x16, x19, x16
    blr x16
done:
    ldp x21, x22, [sp, #32]
    ldp x19, x20, [sp, #16]
    ldp x29, x30, [sp], #48
    ret
.balign 8
resident_mailbox:
    .byte 0, 255, 0, 0
    .word 0
    .word 0
    .word 0
.ltorg
