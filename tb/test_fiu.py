# b2026 test_fiu v0.1 (20260821)
# Bit-level golden model comparison for the Field Isolation Unit.

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

NWORDS = 64  # test memory size in 32-bit words
M32 = 0xFFFFFFFF


# ---------- golden model: bit-addressable memory over 32-bit words ----------

def get_bits(mem, fa, ln):
    val = 0
    for i in range(ln):
        b = fa + i
        bit = (mem.get(b >> 5, 0) >> (b & 31)) & 1
        val |= bit << i
    return val


def set_bits(mem, fa, ln, data):
    for i in range(ln):
        b = fa + i
        w, pos = b >> 5, b & 31
        old = mem.get(w, 0)
        if (data >> i) & 1:
            mem[w] = old | (1 << pos)
        else:
            mem[w] = old & ~(1 << pos) & M32


# ---------- behavioral synchronous single-port memory ----------

async def mem_proc(dut, mem):
    while True:
        await FallingEdge(dut.clk)
        addr = int(dut.m_addr.value) % NWORDS
        re = int(dut.m_re.value)
        we = int(dut.m_we.value)
        wd = int(dut.m_wdata.value)
        pending = mem.get(addr, 0) if re else None
        await RisingEdge(dut.clk)
        if we:
            mem[addr] = wd
        if pending is not None:
            dut.m_rdata.value = pending


# ---------- request driver ----------

async def op(dut, wr, fa, ln, fd=0, wdata=0):
    dut.req.value = 1
    dut.wr.value = wr
    dut.fa.value = fa
    dut.len.value = ln
    dut.fd.value = fd
    dut.wdata.value = wdata
    await RisingEdge(dut.clk)
    dut.req.value = 0
    for _ in range(10):
        await RisingEdge(dut.clk)
        if int(dut.done.value):
            return int(dut.rfield.value)
    raise AssertionError("FIU timeout")


async def setup(dut, seed):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.req.value = 0
    dut.m_rdata.value = 0
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    rng = random.Random(seed)
    hw = {i: rng.getrandbits(32) for i in range(NWORDS)}
    ref = dict(hw)
    cocotb.start_soon(mem_proc(dut, hw))
    return rng, hw, ref


BITLIMIT = (NWORDS - 1) * 32  # keep w0+1 in range


@cocotb.test()
async def random_read_write(dut):
    """Mixed random reads and writes against the bit-level model."""
    rng, hw, ref = await setup(dut, 1972)
    for _ in range(300):
        ln = rng.randint(1, 32)
        fa = rng.randint(0, BITLIMIT - ln)
        if rng.random() < 0.5:
            got = await op(dut, 0, fa, ln)
            exp = get_bits(ref, fa, ln)
            assert got == exp, f"read fa={fa} len={ln}: {got:x} != {exp:x}"
        else:
            wd = rng.getrandbits(ln)
            old = await op(dut, 1, fa, ln, wdata=wd)
            exp_old = get_bits(ref, fa, ln)
            assert old == exp_old, (
                f"swap fa={fa} len={ln}: old {old:x} != {exp_old:x}")
            set_bits(ref, fa, ln, wd)
    for w in range(NWORDS):
        assert hw.get(w, 0) == ref.get(w, 0), (
            f"word {w}: {hw.get(w,0):08x} != {ref.get(w,0):08x}")


@cocotb.test()
async def wilner_property(dut):
    """L bits forward from a equal L bits backward from a+L."""
    rng, hw, ref = await setup(dut, 13)
    for _ in range(100):
        ln = rng.randint(1, 32)
        fa = rng.randint(0, BITLIMIT - ln)
        fwd = await op(dut, 0, fa, ln, fd=0)
        bwd = await op(dut, 0, fa + ln, ln, fd=1)
        assert fwd == bwd, f"fa={fa} len={ln}: fwd {fwd:x} != bwd {bwd:x}"
        assert fwd == get_bits(ref, fa, ln)


@cocotb.test()
async def boundary_cases(dut):
    """Worst-case offsets: fields straddling word boundaries."""
    rng, hw, ref = await setup(dut, 7)
    cases = []
    for w in (0, 1, 30, 62):
        for o in (0, 1, 15, 31):
            for ln in (1, 2, 31, 32):
                fa = w * 32 + o
                if fa + ln <= BITLIMIT:
                    cases.append((fa, ln))
    for fa, ln in cases:
        got = await op(dut, 0, fa, ln)
        exp = get_bits(ref, fa, ln)
        assert got == exp, f"read fa={fa} len={ln}: {got:x} != {exp:x}"
    for fa, ln in cases:
        wd = rng.getrandbits(ln)
        await op(dut, 1, fa, ln, wdata=wd)
        set_bits(ref, fa, ln, wd)
        got = await op(dut, 0, fa, ln)
        assert got == wd, f"rmw fa={fa} len={ln}: {got:x} != {wd:x}"
    for w in range(NWORDS):
        assert hw.get(w, 0) == ref.get(w, 0), f"word {w} mismatch"
