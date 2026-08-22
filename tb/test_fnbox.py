# b2026 test_fnbox v0.1 (20260821)
# Golden-model comparison for the CPL-biased function box.

import random
import cocotb
from cocotb.triggers import Timer

M32 = 0xFFFFFFFF


def model(x, y, cpl):
    mask = M32 if cpl >= 32 else ((1 << cpl) - 1)
    xm, ym = x & mask, y & mask
    s = xm + ym
    d = (xm - ym) & ((1 << 33) - 1)
    out = {
        "sum": s & mask & M32,
        "diff": d & mask & M32,
        "andr": xm & ym,
        "orr": xm | ym,
        "xorr": xm ^ ym,
        "mskx": xm,
    }
    out["cyl"] = (s >> cpl) & 1
    out["z"] = 1 if out["sum"] == 0 else 0
    out["n"] = (out["sum"] >> (cpl - 1)) & 1
    return out


async def check(dut, x, y, cpl):
    dut.x.value = x
    dut.y.value = y
    dut.cpl.value = cpl
    await Timer(1, unit="ns")
    exp = model(x, y, cpl)
    for name in ("sum", "diff", "andr", "orr", "xorr", "mskx", "cyl", "z", "n"):
        got = int(getattr(dut, name).value)
        assert got == exp[name], (
            f"{name}: x={x:08x} y={y:08x} cpl={cpl} "
            f"got={got:x} exp={exp[name]:x}"
        )


@cocotb.test()
async def edges(dut):
    """Edge CPL values with adversarial operands."""
    ops = [0, 1, M32, 0x80000000, 0x7FFFFFFF, 0xAAAAAAAA, 0x55555555]
    for cpl in (1, 2, 7, 8, 15, 16, 31, 32):
        for x in ops:
            for y in ops:
                await check(dut, x, y, cpl)


@cocotb.test()
async def random_vectors(dut):
    """Randomized sweep across all CPL values."""
    rng = random.Random(1700)
    for _ in range(2000):
        cpl = rng.randint(1, 32)
        x = rng.getrandbits(32)
        y = rng.getrandbits(32)
        await check(dut, x, y, cpl)
