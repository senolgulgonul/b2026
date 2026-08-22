// b2026 compliance env v0.1 (20260821)
// Minimal riscv-test-env replacement for the b2026 soft machine.
// Pass: a0 = 1, ecall. Fail: a0 = testnum*2+1, ecall.
#ifndef _ENV_B2026_TEST_H
#define _ENV_B2026_TEST_H

#define RVTEST_RV32U
#define TESTNUM gp

#define RVTEST_CODE_BEGIN \
        .section .text.init; \
        .globl _start; \
_start:

#define RVTEST_CODE_END

#define RVTEST_PASS \
        li a0, 1; \
        ecall

#define RVTEST_FAIL \
        slli a0, TESTNUM, 1; \
        ori a0, a0, 1; \
        ecall

#define RVTEST_DATA_BEGIN .data; .align 4;
#define RVTEST_DATA_END .align 4;

#endif
