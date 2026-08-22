# b2026 test_bench_cpi v0.1 (20260822)
# Runs the same reference workload (sum 1..100, store low six bits to
# the LED port) on the b2026 RV32I interpreter and reports cycles,
# for the comparison table.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from ucode_rv32i import build_interpreter, rv_asm, CODE_BYTE

NWORDS = 4096
HALTW = 0xF100


async def cs_proc(dut, prog):
    while True:
        await FallingEdge(dut.clk)
        a, re = int(dut.cs_addr.value), int(dut.cs_re.value)
        await RisingEdge(dut.clk)
        if re:
            dut.cs_rdata.value = prog.get(a, HALTW)


async def smem_proc(dut, mem):
    while True:
        await FallingEdge(dut.clk)
        a = int(dut.m_addr.value) % NWORDS
        re, we = int(dut.m_re.value), int(dut.m_we.value)
        wd = int(dut.m_wdata.value)
        pending = mem.get(a, 0) if re else None
        await RisingEdge(dut.clk)
        if we:
            mem[a] = wd
        if pending is not None:
            dut.m_rdata.value = pending


@cocotb.test()
async def reference_workload(dut):
    """sum 1..100 = 5050, low six bits 58; count cycles to ECALL."""
    rv = rv_asm([
        ('addi', 1, 0, 100),
        ('addi', 2, 0, 0),
        ('label', 'loop'),
        ('add', 2, 2, 1),
        ('addi', 1, 1, -1),
        ('bne', 1, 0, 'loop'),
        ('andi', 3, 2, 63),
        ('addi', 10, 3, 0),
        ('ecall',),
    ])
    prog = build_interpreter()
    smem = {CODE_BYTE // 4 + i: w for i, w in enumerate(rv)}
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.uart_rxp.value = 1
    dut.cs_rdata.value = HALTW
    dut.m_rdata.value = 0
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    cocotb.start_soon(cs_proc(dut, prog))
    cocotb.start_soon(smem_proc(dut, smem))
    n = 0
    for _ in range(2_000_000):
        n += 1
        await FallingEdge(dut.clk)
        if int(dut.halted.value):
            break
    else:
        raise AssertionError("no halt")
    assert int(dut.mon.value) == 58, int(dut.mon.value)
    instrs = 2 + 3 * 100 + 3          # executed RV32I instructions
    dut._log.info(f"B2026 cycles={n} instr={instrs} "
                  f"cpi={n/instrs:.1f} led=58")
