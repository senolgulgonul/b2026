OUTPUT_ARCH("riscv")
ENTRY(_start)
SECTIONS { . = 0x100; .text : { *(.text.init) *(.text*) } }
