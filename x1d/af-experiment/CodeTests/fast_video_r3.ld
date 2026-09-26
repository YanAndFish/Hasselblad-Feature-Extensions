/* 仅用于电脑ARM模拟器；这段地址不是已核对的实机空闲区域。 */
ENTRY(fast_video_wait)
SECTIONS {
 . = 0x300000;
 .text : { *(.text*) }
 .rodata : { *(.rodata*) }
 . = ALIGN(32);
 .data : { *(.data*) }
 .bss : { *(.bss*) }
 . = ALIGN(32);
 __payload_end = .;
 ASSERT(. < 0x310000, "offline model overflow")
 /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment) *(.note*) }
}
