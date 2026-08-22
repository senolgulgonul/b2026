# b2026 test_fpga v0.3 (20260821)
# Boot the FPGA top from its init images. Power-on now enters the Gismo
# console (banner over UART TX); 'G' boots the preloaded RV32I demo.

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

BAUD = 234  # board-real divider


async def send_byte(dut, b):
    dut.uart_rx.value = 0
    for _ in range(BAUD):
        await RisingEdge(dut.sys_clk)
    for i in range(8):
        dut.uart_rx.value = (b >> i) & 1
        for _ in range(BAUD):
            await RisingEdge(dut.sys_clk)
    dut.uart_rx.value = 1
    for _ in range(BAUD + 2):
        await RisingEdge(dut.sys_clk)


async def run_demo(dut, budget=900000):
    # 'G' may arrive while the banner is printing; the receiver holds it
    await send_byte(dut, ord('G'))
    for i in range(budget):
        await FallingEdge(dut.sys_clk)
        if int(dut.u_core.halted.value):
            return i
    raise AssertionError("demo did not halt")


@cocotb.test()
async def console_boot_then_demo(dut):
    cocotb.start_soon(Clock(dut.sys_clk, 37, unit="ns").start())
    dut.btn1_n.value = 1
    dut.uart_rx.value = 1
    for _ in range(33000):                     # power-on reset counter
        await RisingEdge(dut.sys_clk)
    cycles = await run_demo(dut)
    mon = int(dut.u_core.mon.value)
    led = int(dut.led.value)
    dut._log.info(f"halted after {cycles} cycles, mon={mon}, led={led:06b}")
    assert mon == 55 and led == (~55) & 0x3F


@cocotb.test()
async def button_reset_reenters_console(dut):
    cocotb.start_soon(Clock(dut.sys_clk, 37, unit="ns").start())
    dut.uart_rx.value = 1
    dut.btn1_n.value = 0
    for _ in range(10):
        await RisingEdge(dut.sys_clk)
    dut.btn1_n.value = 1
    for _ in range(10):
        await RisingEdge(dut.sys_clk)
    await run_demo(dut)
    assert int(dut.u_core.mon.value) == 55
