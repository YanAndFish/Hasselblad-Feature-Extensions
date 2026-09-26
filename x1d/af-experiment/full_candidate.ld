ENTRY(dispatch_entry)
SECTIONS {
  . = 0x2b2880;
  .text : { KEEP(*(.text.entry)) *(.text*) }
  .rodata : { *(.rodata*) }
  . = ALIGN(32);
  .data : { KEEP(*(.data.state)) *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  . = ALIGN(32);
  __payload_end = .;
  ASSERT(. <= 0x2b4000, "AF payload exceeds verified alignment area")
  /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
}
