# b2026 test_rv32i v0.3 (20260821)
# Full-interpreter tests: DUT final architectural state compared against
# the golden ISS after running the same RV32I program.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from ucode_rv32i import (build_interpreter, rv_asm, ISS, M32, CODE_BYTE)

NWORDS = 512
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


async def run_and_compare(dut, rvwords, max_cycles=400000,
                          check_words=None):
    prog = build_interpreter()
    smem = {CODE_BYTE // 4 + i: w for i, w in enumerate(rvwords)}
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.cs_rdata.value = HALTW
    dut.m_rdata.value = 0
    dut.uart_rxp.value = 1
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    cocotb.start_soon(cs_proc(dut, prog))
    cocotb.start_soon(smem_proc(dut, smem))
    cycles = 0
    for _ in range(max_cycles):
        cycles += 1
        await FallingEdge(dut.clk)
        if int(dut.halted.value):
            break
    else:
        raise AssertionError("no ECALL within budget")
    iss0 = ISS(rvwords); iss0.run()
    assert int(dut.mon.value) == (iss0.x[10] & 0xFF)
    iss = ISS(rvwords)
    iss.run()
    for r in range(32):
        got, exp = smem.get(r, 0), iss.x[r]
        assert got == exp, f"x{r}: dut {got:08x} != iss {exp:08x}"
    for w in (check_words or []):
        got, exp = smem.get(w, 0), iss.mem.get(w, 0)
        assert got == exp, f"mem[{w}]: dut {got:08x} != iss {exp:08x}"
    return cycles


@cocotb.test()
async def alu_and_upper(dut):
    """Arithmetic, logic, shifts, compares, LUI/AUIPC vs the ISS."""
    rv = rv_asm([
        ('lui', 1, 0x12345),
        ('addi', 1, 1, 0x678),
        ('addi', 2, 0, -100),
        ('add', 3, 1, 2),
        ('sub', 4, 1, 2),
        ('and', 5, 1, 2),
        ('or', 6, 1, 2),
        ('xor', 7, 1, 2),
        ('slt', 8, 2, 1),
        ('slt', 9, 1, 2),
        ('sltu', 10, 2, 1),
        ('sltu', 11, 1, 2),
        ('slti', 12, 2, 5),
        ('sltiu', 13, 2, 5),
        ('xori', 14, 1, -1),
        ('ori', 15, 1, 0x7FF),
        ('andi', 16, 1, 0x7FF),
        ('slli', 17, 1, 4),
        ('srli', 18, 1, 8),
        ('srai', 19, 2, 4),
        ('sll', 20, 1, 12),
        ('srl', 21, 1, 8),
        ('sra', 22, 2, 8),
        ('slli', 23, 1, 0),
        ('srai', 24, 2, 0),
        ('auipc', 25, 1),
        ('auipc', 26, 0),
        ('sltiu', 27, 0, 1),
        ('ecall',),
    ])
    cycles = await run_and_compare(dut, rv)
    n = len(rv)
    dut._log.info(f"alu: {cycles} cycles, {n} instr, {cycles/n:.1f} cpi")


@cocotb.test()
async def memory_ops(dut):
    """Loads and stores of all widths, signed and unsigned, unaligned."""
    rv = rv_asm([
        ('addi', 1, 0, 1024),          # data base, byte 1024 (word 256)
        ('addi', 2, 0, -2),            # 0xFFFFFFFE
        ('sw', 2, 0, 1),
        ('lw', 3, 0, 1),
        ('lbu', 4, 0, 1),
        ('lb', 5, 0, 1),
        ('lhu', 6, 0, 1),
        ('lh', 7, 0, 1),
        ('addi', 8, 0, 0x77),
        ('sb', 8, 5, 1),
        ('sh', 8, 8, 1),
        ('lw', 9, 4, 1),
        ('lb', 10, 3, 1),
        ('sb', 2, 2, 1),
        ('lw', 11, 0, 1),
        ('lhu', 12, 1, 1),             # unaligned halfword
        ('lw', 13, 2, 1),              # unaligned word, crosses words
        ('sh', 2, 13, 1),              # unaligned store
        ('lw', 14, 12, 1),
        ('ecall',),
    ])
    cycles = await run_and_compare(dut, rv,
                                   check_words=list(range(256, 262)))
    n = len(rv)
    dut._log.info(f"mem: {cycles} cycles, {n} instr, {cycles/n:.1f} cpi")


@cocotb.test()
async def control_flow(dut):
    """All six branches both ways, JAL/JALR call and return."""
    rv = rv_asm([
        ('addi', 1, 0, -1),
        ('addi', 2, 0, 1),
        # taken cases: marker register must stay 0
        ('blt', 1, 2, 'a1'), ('addi', 20, 0, 1), ('label', 'a1'),
        ('bge', 2, 1, 'a2'), ('addi', 21, 0, 1), ('label', 'a2'),
        ('bltu', 2, 1, 'a3'), ('addi', 22, 0, 1), ('label', 'a3'),
        ('bgeu', 1, 2, 'a4'), ('addi', 23, 0, 1), ('label', 'a4'),
        ('beq', 1, 1, 'a5'), ('addi', 24, 0, 1), ('label', 'a5'),
        ('bne', 1, 2, 'a6'), ('addi', 25, 0, 1), ('label', 'a6'),
        # not-taken cases: marker register must become 1
        ('blt', 2, 1, 'b1'), ('addi', 26, 0, 1), ('label', 'b1'),
        ('bge', 1, 2, 'b2'), ('addi', 27, 0, 1), ('label', 'b2'),
        ('bltu', 1, 2, 'b3'), ('addi', 28, 0, 1), ('label', 'b3'),
        ('bgeu', 2, 1, 'b4'), ('addi', 29, 0, 1), ('label', 'b4'),
        ('beq', 1, 2, 'b5'), ('addi', 30, 0, 1), ('label', 'b5'),
        ('bne', 1, 1, 'b6'), ('addi', 31, 0, 1), ('label', 'b6'),
        # call/return with JAL and JALR
        ('jal', 5, 'func'),
        ('addi', 7, 6, 100),           # after return: x7 = x6 + 100
        ('jal', 0, 'end'),
        ('label', 'func'),
        ('addi', 6, 0, 42),
        ('jalr', 0, 5, 0),             # return
        ('label', 'end'),
        ('auipc', 9, 0),
        ('jalr', 10, 9, 12),           # skip the next instruction
        ('addi', 11, 0, 999),          # must be skipped
        ('addi', 12, 10, 0),           # x12 = link of jalr
        ('ecall',),
    ])
    cycles = await run_and_compare(dut, rv)
    dut._log.info(f"ctl: {cycles} cycles")


@cocotb.test()
async def sum_loop(dut):
    """The classic: sum 10..1 must give 55 in x2."""
    rv = rv_asm([
        ('addi', 1, 0, 10),
        ('addi', 2, 0, 0),
        ('label', 'loop'),
        ('add', 2, 2, 1),
        ('addi', 1, 1, -1),
        ('bne', 1, 0, 'loop'),
        ('ecall',),
    ])
    cycles = await run_and_compare(dut, rv)
    n = 2 + 10 * 3 + 1
    dut._log.info(f"loop: {cycles} cycles, {n} instr, {cycles/n:.1f} cpi")
