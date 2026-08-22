OUTPUT_ARCH("riscv")
ENTRY(_start)
SECTIONS
{
  . = 0x100;
  .text : { *(.text.init) *(.text*) }
  . = ALIGN(16);
  .data : { *(.data*) *(.sdata*) *(.srodata*) *(.rodata*) }
  .bss  : { *(.bss*) *(.sbss*) }
}
