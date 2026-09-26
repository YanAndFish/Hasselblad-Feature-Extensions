ENTRY(na_direction)
/* 纯仿真地址，未核实为相机可用 RAM，不可送入任何现有装载器。 */
SECTIONS { . = 0x800000; .text : { KEEP(*(.text.na_api)) *(.text*) } .rodata : { *(.rodata*) }
 . = ALIGN(32); .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) }
 . = ALIGN(32); __payload_end = .;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(. <= 0x810000, "offline image exceeds mapped test arena") }
