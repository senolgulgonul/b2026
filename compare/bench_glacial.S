/* Glacial variant of the reference workload: same sum 1..100, but the
 * result byte goes to Glacial's memory-mapped output. Glacial has no
 * LED port, so we store to a known RAM byte and the wrapper latches it.
 */
    .section .text.init
    .globl _start
_start:
    li   x1, 100
    li   x2, 0
loop:
    add  x2, x2, x1
    addi x1, x1, -1
    bne  x1, x0, loop
    andi x3, x2, 63
    li   x4, 0x1FFC
    sw   x3, 0(x4)
spin:
    j    spin
