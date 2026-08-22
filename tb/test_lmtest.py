# b2026 test_lmtest v0.2 (20260822)
# Simulate exactly what b26_lmtest.py sends: bare-microcode L test and
# the memory-peek L+M test, twice with different values.

import os, sys
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "fpga"))
from ucode_rv32i import build_gismo, strings_words
from test_loader import (cs_proc, smem_proc, send_bytes, wait_halt,
                         tx_capture)
import importlib.util
spec = importlib.util.spec_from_file_location(
    "b26_lmtest", os.path.join(os.path.dirname(__file__),
                               "..", "fpga", "b26_lmtest.py"))
lm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lm)


@cocotb.test()
async def l_and_m_exercises(dut):
    holder = {'cs': dict(build_gismo())}
    sw, sa = strings_words()
    smem = {sa + i: w for i, w in enumerate(sw)}
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.uart_rxp.value = 1
    dut.cs_rdata.value = 0xF100
    dut.m_rdata.value = 0
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    cocotb.start_soon(cs_proc(dut, holder))
    cocotb.start_soon(smem_proc(dut, smem))
    txbuf = []
    cocotb.start_soon(tx_capture(dut, txbuf))
    assert await wait_halt(dut, 100)

    for mode, val in (('l', 42), ('l', 7), ('m', 33), ('m', 60)):
        await send_bytes(dut, lm.make_stream(mode, val))
        assert await wait_halt(dut, 20000), f"{mode} {val} no halt"
        for _ in range(8000):
            await RisingEdge(dut.clk)
            if bytes(txbuf).endswith(b'\r\n'):
                break
        said = bytes(txbuf).decode('ascii', 'replace')
        txbuf.clear()
        mon = int(dut.mon.value)
        dut._log.info(f"{mode} {val}: mon={mon}, console={said!r}")
        assert mon == val and said == f"{val:08X}\r\n" 
