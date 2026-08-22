# b2026 test_b26 v0.1 (20260821)
# End-to-end tests: hand-assembled microprograms running on the full
# micromachine, checked against a bit-level S-memory model.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

M32 = 0xFFFFFFFF
NWORDS = 64
HALTW = 0xF100

# ---------- register names ----------
RX, RY, RT = 0x10, 0x11, 0x12
FA_, FL_, SFA, SFL, RCPL = 0x13, 0x14, 0x15, 0x16, 0x17
SUM, DIFF, ANDR, ORR, XORR, MSKX, ZERO, ONES = (
    0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F)
# 4-bit compact map for READ dest / WRITE src
C_X, C_Y, C_T = 12, 13, 14

# ---------- encoders ----------
def MOVE(src, dst):  return 0x0000 | (src << 6) | dst
def LIT(v):          return 0x1000 | (v & 0xFFF)
def LITS(v):         return 0x2000 | (v & 0xFFF)
def RD(d4, sf=0, cnt=0, ln=0):
    return 0x3000 | (d4 << 8) | (sf << 7) | (cnt << 5) | (ln & 0x1F)
def WR(s4, sf=0, cnt=0, ln=0):
    return 0x4000 | (s4 << 8) | (sf << 7) | (cnt << 5) | (ln & 0x1F)
def EXTI(pos):       return 0x5000 | ((pos & 0x3F) << 6)
def BR(off):         return 0x6000 | (off & 0xFFF)
def IF(c, off):      return 0x7000 | (c << 8) | (off & 0xFF)
def DISP(page):      return 0xA000 | ((page & 0xF) << 8)
def BIASL(n):        return 0xB000 | (n & 0x3F)
def MON(v):          return 0xF200 | (v & 0xFF)
def HALT():          return HALTW

COND_FLNZ = 7

# ---------- golden bit memory helpers ----------
def get_bits(mem, fa, ln):
    val = 0
    for i in range(ln):
        b = fa + i
        val |= ((mem.get(b >> 5, 0) >> (b & 31)) & 1) << i
    return val

def set_bits(mem, fa, ln, data):
    for i in range(ln):
        b = fa + i
        w, pos = b >> 5, b & 31
        old = mem.get(w, 0)
        mem[w] = (old | (1 << pos)) if ((data >> i) & 1) \
            else (old & ~(1 << pos) & M32)

# ---------- behavioral memories ----------
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

async def run(dut, prog, smem, max_cycles=3000):
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
    for _ in range(max_cycles):
        await FallingEdge(dut.clk)
        if int(dut.halted.value):
            return
    raise AssertionError("no HALT within budget")


# ---------- tests ----------

@cocotb.test()
async def add_two_fields(dut):
    """Fetch two 32-bit fields with counting reads, add, store."""
    smem = {0: 0x11223344, 1: 0xDEADBEEF}
    prog = {
        0: BIASL(32),
        1: LIT(0),
        2: MOVE(RT, FA_),
        3: RD(C_X, cnt=3),        # X <- mem[0..32), F.A += 32
        4: RD(C_Y, cnt=3),        # Y <- mem[32..64), F.A += 32
        5: MOVE(SUM, 0),          # S0 <- X + Y
        6: WR(0),                 # mem[64..96) <- S0
        7: MON(0xAB),
        8: HALT(),
    }
    await run(dut, prog, smem)
    exp = (0x11223344 + 0xDEADBEEF) & M32
    assert smem.get(2, 0) == exp, f"{smem.get(2,0):08x} != {exp:08x}"
    assert int(dut.mon.value) == 0xAB


@cocotb.test()
async def unaligned_rmw(dut):
    """Wilner's numbers: a 13-bit field written at bit address 13."""
    smem = {0: 0xFFFFFFFF, 1: 0xFFFFFFFF}
    ref = dict(smem)
    prog = {
        0: BIASL(13),
        1: LIT(13),
        2: MOVE(RT, FA_),
        3: LIT(0x1),              # 13-bit 0x1234 built as LIT + LITS
        4: LITS(0x234),
        5: MOVE(RT, 1),           # S1 <- T
        6: WR(1),                 # 13 bits at bit 13 <- S1
        7: RD(C_X),               # X <- same field back
        8: MOVE(RX, 2),           # S2 <- X (observable later if needed)
        9: HALT(),
    }
    await run(dut, prog, smem)
    set_bits(ref, 13, 13, 0x1234)
    for w in range(4):
        assert smem.get(w, 0) == ref.get(w, 0), (
            f"word {w}: {smem.get(w,0):08x} != {ref.get(w,0):08x}")
    assert get_bits(smem, 13, 13) == 0x1234


@cocotb.test()
async def loop_sum_words(dut):
    """Counting read loop over 4 words, FL0-terminated, result stored."""
    words = [0x10000001, 0x20000002, 0x30000003, 0x0FFFFFFA]
    smem = {i: w for i, w in enumerate(words)}
    prog = {
        0: BIASL(32),
        1: LIT(0),
        2: MOVE(RT, FA_),
        3: LIT(128),
        4: MOVE(RT, FL_),
        5: LIT(0),
        6: MOVE(RT, RY),          # accumulator
        7: RD(C_X, cnt=1),        # X <- next word, F.A += 32, F.L -= 32
        8: MOVE(SUM, RY),         # Y <- X + Y
        9: IF(COND_FLNZ, -2),     # loop while F.L != 0
        10: MOVE(RY, 0),          # S0 <- total
        11: LIT(512),
        12: MOVE(RT, SFA),        # result at bit 512 (word 16)
        13: WR(0, sf=1),
        14: MON(0x99),
        15: HALT(),
    }
    await run(dut, prog, smem)
    exp = sum(words) & M32
    assert smem.get(16, 0) == exp, f"{smem.get(16,0):08x} != {exp:08x}"
    assert int(dut.mon.value) == 0x99


@cocotb.test()
async def ext_dispatch(dut):
    """EXT a 4-bit opcode out of X, DISP to its handler."""
    smem = {}
    prog = {
        0: BIASL(4),
        1: LIT(0x25),
        2: MOVE(RT, RX),
        3: EXTI(0),               # T <- X[3:0] = 5
        4: DISP(0),               # -> address 5
        5: MON(0x55),
        6: HALT(),
    }
    await run(dut, prog, smem)
    assert int(dut.mon.value) == 0x55
