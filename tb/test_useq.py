# b2026 test_useq v0.1 (20260821)
# Architectural golden model for the microsequencer. The pipeline must be
# invisible: the executed-address trace has to match a plain interpreter,
# with and without random stalls.

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

HALTW = 0xF100  # CTRL/HALT, also the default for unmapped addresses


# ---------- encoders ----------

def DP():           return 0x0000            # any datapath op
def BR(off):        return 0x6000 | (off & 0xFFF)
def IF(c, off):     return 0x7000 | (c << 8) | (off & 0xFF)
def CALL(t):        return 0x8000 | (t & 0xFFF)
def EXIT():         return 0x9000
def DISP(page):     return 0xA000 | ((page & 0xF) << 8)
def NOP():          return 0xF000
def HALT():         return HALTW


def sext(v, bits):
    m = 1 << (bits - 1)
    return (v & (m - 1)) - (v & m)


def cond_val(c, fl):
    z, cyl, n, fl0, sfl0, intr = fl
    table = [z, not z, cyl, not cyl, n, not n,
             fl0, not fl0, sfl0, not sfl0, intr, True]
    return table[c] if c < 12 else False


# ---------- architectural golden model ----------

def golden(prog, flags, disp_t, max_steps=500):
    pc, sp, stk = 0, 0, [0] * 16
    trace = []
    for _ in range(max_steps):
        w = prog.get(pc, HALTW)
        trace.append(pc)
        cls = w >> 12
        if cls == 0xF and ((w >> 8) & 0xF) == 1:
            return trace, True
        if cls == 0x6:
            pc = (pc + sext(w & 0xFFF, 12)) & 0xFFF
        elif cls == 0x7:
            if cond_val((w >> 8) & 0xF, flags):
                pc = (pc + sext(w & 0xFF, 8)) & 0xFFF
            else:
                pc = (pc + 1) & 0xFFF
        elif cls == 0x8:
            stk[sp] = (pc + 1) & 0xFFF
            sp = (sp + 1) & 15
            pc = w & 0xFFF
        elif cls == 0x9:
            sp = (sp - 1) & 15
            pc = stk[sp]
        elif cls == 0xA:
            pc = (((w >> 8) & 0xF) << 8) | disp_t
        else:
            pc = (pc + 1) & 0xFFF
    return trace, False


# ---------- DUT harness ----------

async def cs_proc(dut, prog):
    # BSRAM-like: the output register only updates when cs_re (the clock
    # enable) is high; otherwise it holds, which is what keeps uinstr
    # stable across stall cycles.
    while True:
        await FallingEdge(dut.clk)
        a = int(dut.cs_addr.value)
        re = int(dut.cs_re.value)
        await RisingEdge(dut.clk)
        if re:
            dut.cs_rdata.value = prog.get(a, HALTW)


async def run_dut(dut, prog, flags, disp_t, max_cycles=2000, stall_rng=None):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    z, cyl, n, fl0, sfl0, intr = flags
    dut.f_z.value = int(z)
    dut.f_cyl.value = int(cyl)
    dut.f_n.value = int(n)
    dut.f_fl0.value = int(fl0)
    dut.f_sfl0.value = int(sfl0)
    dut.f_int.value = int(intr)
    dut.disp_t.value = disp_t
    dut.stall.value = 0
    dut.cs_rdata.value = HALTW
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    cocotb.start_soon(cs_proc(dut, prog))
    trace = []
    for _ in range(max_cycles):
        # change stall only at the start of a cycle so the combinational
        # cs_re and the sequential state see one consistent value
        await RisingEdge(dut.clk)
        s = 0
        if stall_rng is not None:
            s = 1 if stall_rng.random() < 0.4 else 0
        dut.stall.value = s
        await FallingEdge(dut.clk)
        if int(dut.halted.value):
            return trace, True
        if int(dut.uvalid.value) and not s:
            trace.append(int(dut.upc.value))
    return trace, False


async def compare(dut, prog, flags=(0, 0, 0, 0, 0, 0), disp_t=0,
                  stall_rng=None):
    exp, ehalt = golden(prog, flags, disp_t)
    got, ghalt = await run_dut(dut, prog, flags, disp_t,
                               stall_rng=stall_rng)
    assert ghalt and ehalt, f"halt mismatch: dut={ghalt} gold={ehalt}"
    assert got == exp, f"trace mismatch:\n dut  {got}\n gold {exp}"


# ---------- tests ----------

@cocotb.test()
async def linear_halt(dut):
    """Straight-line datapath ops end in HALT."""
    prog = {0: DP(), 1: DP(), 2: NOP(), 3: DP(), 4: HALT()}
    await compare(dut, prog)


@cocotb.test()
async def branches_calls(dut):
    """Forward and backward BR, nested CALL/EXIT."""
    prog = {
        0: BR(4),        # -> 4
        2: HALT(),       # backward-branch target
        4: DP(),
        5: CALL(8),      # -> 8, push 6
        6: BR(-4),       # -> 2, HALT
        8: DP(),
        9: CALL(12),     # push 10
        10: EXIT(),      # -> 6
        12: DP(),
        13: EXIT(),      # -> 10
    }
    await compare(dut, prog)


@cocotb.test()
async def all_conditions(dut):
    """Every IF condition, taken and not taken."""
    for c in range(12):
        for bits in (0, 1):
            flags = (bits,) * 6
            prog = {0: IF(c, 2), 1: DP(), 2: HALT()}
            await compare(dut, prog, flags=flags)


@cocotb.test()
async def dispatch(dut):
    """DISP jumps to {page, T}."""
    prog = {0: DISP(2), 0x237: DP(), 0x238: HALT()}
    await compare(dut, prog, disp_t=0x37)


@cocotb.test()
async def stall_invariance(dut):
    """Random stalls must not change the executed trace."""
    prog = {
        0: BR(4), 2: HALT(), 4: DP(), 5: CALL(8), 6: BR(-4),
        8: DP(), 9: CALL(12), 10: EXIT(), 12: DP(), 13: EXIT(),
    }
    await compare(dut, prog, stall_rng=random.Random(1700))
