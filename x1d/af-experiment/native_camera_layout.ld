ENTRY(na_direction_bridge)
/* 仅供离线体积测量；0x800000 不是已验证相机空闲地址。 */
SECTIONS {
 . = 0x800000;
 .text : { KEEP(*(.text.camera_bridges)) KEEP(*(.text.na_api)) *(.text*) }
 .rodata : { *(.rodata*) }
 . = ALIGN(32); __state_start = .;
 .data : { *(.data*) } .bss : { *(.bss*) *(COMMON) }
 . = ALIGN(32); __payload_end = .;
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
 ASSERT(. <= 0x810000, "offline measurement arena overflow")
}
