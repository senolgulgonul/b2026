# b2026 test_compliance v0.2 (20260821)
# Official riscv-tests rv32ui suite. Single persistent clock and memory
# processes; per-test state swapped in place (no task kill/respawn).

import glob
import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from ucode_rv32i import build_interpreter

NWORDS = 32768
HALTW = 0xF100
BINDIR = os.path.join(os.path.dirname(__file__), "..", "compliance", "bins")


def load_bin(path):
    with open(path, "rb") as f:
        data = f.read()
    data += b"\x00" * (-len(data) % 4)
    return {0x100 // 4 + i // 4: int.from_bytes(data[i:i+4], "little")
            for i in range(0, len(data), 4)}


async def cs_proc(dut, holder):
    while True:
        await FallingEdge(dut.clk)
        a, re = int(dut.cs_addr.value), int(dut.cs_re.value)
        await RisingEdge(dut.clk)
        if re:
            dut.cs_rdata.value = holder['cs'].get(a, HALTW)


async def smem_proc(dut, holder):
    while True:
        await FallingEdge(dut.clk)
        a = int(dut.m_addr.value) % NWORDS
        re, we = int(dut.m_re.value), int(dut.m_we.value)
        wd = int(dut.m_wdata.value)
        pending = holder['sm'].get(a, 0) if re else None
        await RisingEdge(dut.clk)
        if we:
            holder['sm'][a] = wd
        if pending is not None:
            dut.m_rdata.value = pending


async def run_one(dut, holder, smem, max_cycles=1_000_000):
    holder['sm'] = smem
    dut.uart_rxp.value = 1
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    for i in range(max_cycles):
        await FallingEdge(dut.clk)
        if int(dut.halted.value):
            return i
    return None


@cocotb.test()
async def rv32ui_suite(dut):
    """Run every rv32ui test binary and require a0 == 1 from each."""
    holder = {'cs': build_interpreter(), 'sm': {}}
    bins = sorted(glob.glob(os.path.join(BINDIR, "*.bin")))
    assert bins, f"no test binaries in {BINDIR}"
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.cs_rdata.value = HALTW
    dut.m_rdata.value = 0
    cocotb.start_soon(cs_proc(dut, holder))
    cocotb.start_soon(smem_proc(dut, holder))
    failures, total_cycles = [], 0
    for path in bins:
        name = os.path.basename(path)[:-4]
        smem = load_bin(path)
        cycles = await run_one(dut, holder, smem)
        if cycles is None:
            failures.append(f"{name}: TIMEOUT")
            dut._log.error(f"{name:12s} TIMEOUT")
            continue
        a0 = smem.get(10, 0)
        total_cycles += cycles
        if a0 == 1:
            dut._log.info(f"{name:12s} PASS  {cycles} cycles")
        else:
            failures.append(f"{name}: a0={a0:#x} (test {a0 >> 1})")
            dut._log.error(f"{name:12s} FAIL  a0={a0:#x} (test {a0 >> 1})")
    dut._log.info(f"rv32ui: {len(bins) - len(failures)}/{len(bins)} passed, "
                  f"{total_cycles} total cycles")
    assert not failures, "failed: " + "; ".join(failures)
