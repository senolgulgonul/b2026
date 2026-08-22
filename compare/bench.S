/* b2026 compare benchmark v0.1 (20260822)
 * Reference workload for the CPI table: sum 1..100, then store the low
 * six bits of the result to the LED port at byte 4092 (0xFFC).
 * 100*101/2 = 5050 = 0x13BA, low six bits 0b111010 = 58.
 * Instruction count: 2 + 3*100 + 3 = 305 (plus the final store).
 */
    .section .text.init
    .globl _start
_start:
    li   x1, 100          /* i */
    li   x2, 0            /* acc */
loop:
    add  x2, x2, x1
    addi x1, x1, -1
    bne  x1, x0, loop
    andi x3, x2, 63
    li   x4, 4092
    sw   x3, 0(x4)
spin:
    j    spin
