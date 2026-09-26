ENTRY(dispatch_entry)
SECTIONS {
  /* 开发中布局：各旧函数首字留作独立拒绝入口，不纳入辅助代码。 */
  . = 0x19bfb8;
  .extra5 : { *(.text.extra5) }
  ASSERT(. <= 0x19c310, "R5 extra5 overflow")
  . = 0x19c314;
  .extra6 : { *(.text.fastvideo) }
  ASSERT(. <= 0x19c8ec, "R5 extra6 overflow")
  . = 0x19c8f0;
  .extra7 : { *(.text.extra7) }
  ASSERT(. <= 0x19cc20, "R5 extra7 overflow")
  . = 0x19cc24;
  .extra8 : { *(.text.extra8) }
  ASSERT(. <= 0x19cf5c, "R5 extra8 overflow")
  . = 0x19d1a0;
  .extra1 : { *(.text.extra1) }
  ASSERT(. <= 0x19d5c8, "R5 extra1 overflow")
  . = 0x19d5cc;
  .extra2 : { *(.text.extra2) }
  ASSERT(. <= 0x19d87c, "R5 extra2 overflow")
  . = 0x19d880;
  .extra3 : { *(.text.extra3) }
  ASSERT(. <= 0x19d9cc, "R5 extra3 overflow")
  . = 0x19d9d0;
  .extra4 : { *(.text.extra4) }
  ASSERT(. <= 0x19dd70, "R5 extra4 overflow")
  . = 0x2b2880;
  .text : { KEEP(*(.text.entry)) *(.text*) }
  .rodata : { *(.rodata*) }
  . = ALIGN(32);
  .data : { KEEP(*(.data.state)) *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  . = ALIGN(32);
  __payload_end = .;
  ASSERT(. <= 0x2b3f40, "R5 payload overlaps independent installation barrier")
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
}
