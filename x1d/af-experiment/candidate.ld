ENTRY(state3_entry)
SECTIONS { . = 0x2b2880; .text : { KEEP(*(.text.entry)) KEEP(*(.text*)) } .rodata : { *(.rodata*) } . = ALIGN(32); .data : { *(.data.state) *(.data*) } .bss : { *(.bss*) *(COMMON) } . = ALIGN(32); __payload_end = .; /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) } ASSERT(. <= 0x2b4000, "AF payload exceeds verified arena") }
