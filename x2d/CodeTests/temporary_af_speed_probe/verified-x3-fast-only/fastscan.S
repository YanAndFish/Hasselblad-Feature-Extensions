// First-generation X2D official 4.2.0 libaaa.so ONLY.
// Reordered original dynamic divisor selection; only type 0 is multiplied.
.text

.Ldispatch:
and w8,w21,#0xffff
cmp w8,#5
fmul d0,d9,d0
fcvt s0,d0
b.hi .Ldispatch+56
cbz w8,.Ldispatch+0x124
cmp w8,#3
b.eq .Ldispatch+0x12c
fmov s1,#2.0
mov w9,#0x12
lsr w9,w9,w8
tbnz w9,#0,.Ldispatch+0x130
fdiv s1,s1,s10
b .Ldispatch+0x130
fmov s1,#4.0
b .Ldispatch+0x130
.org 0xdc
// Replace the final conversion with a bounded conversion in the same function.
b .Ldispatch+0x140
.org 0x124

.Lscale:
fmov s1,#3.0
fmul s0,s0,s1
fmov s1,#1.0
.org 0x13c
// Bypass only the successful-calculation verbose diagnostic block.
b .Ldispatch+0xc4
fcvtzs w8,s0
and w9,w21,#0xffff
cbnz w9,.Ldispatch+0xe0
ldr w9,[x24,#4]
cmp w9,#2
b.ne .Ldispatch+0xe0
cmp w8,#0
csel w8,wzr,w8,lt
mov w9,#21844
cmp w8,w9
csel w8,w9,w8,hi
b .Ldispatch+0xe0
