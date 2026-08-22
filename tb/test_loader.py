# b2026 test_loader v0.3 (20260822)
# The soft machine proof: boot with Gismo only, load the stack-machine
# S-language over UART, run it (mon=55), then hot-swap to the RV32I
# interpreter over the same UART and run its demo (mon=55 again).
# Same hardware, same bitstream, two ISAs.
#
# Requires BAUD_DIV=4 (Makefile: COMPILE_ARGS += -Pb26.BAUD_DIV=4).

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge

from ucode_rv32i import (build_gismo, build_stack_interpreter,
                         build_interpreter, stk_asm, rv_asm,
                         loader_stream, strings_words, MENU_TEXT,
                         CODE_BYTE)

NWORDS = 32768
HALTW = 0xF100
BAUD_DIV = 4


async def cs_proc(dut, holder):
    while True:
        await FallingEdge(dut.clk)
        a, re = int(dut.cs_addr.value), int(dut.cs_re.value)
        we = int(dut.cs_we.value)
        wa, wd = int(dut.cs_waddr.value), int(dut.cs_wdata.value)
        pending = holder['cs'].get(a, HALTW) if re else None
        await RisingEdge(dut.clk)
        if we:
            holder['cs'][wa] = wd
        if pending is not None:
            dut.cs_rdata.value = pending


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


async def send_bytes(dut, data):
    for b in data:
        dut.uart_rxp.value = 0                     # start
        for _ in range(BAUD_DIV):
            await RisingEdge(dut.clk)
        for i in range(8):                         # LSB first
            dut.uart_rxp.value = (b >> i) & 1
            for _ in range(BAUD_DIV):
                await RisingEdge(dut.clk)
        dut.uart_rxp.value = 1                     # stop
        for _ in range(BAUD_DIV + 2):
            await RisingEdge(dut.clk)


async def tx_capture(dut, sink):
    while True:
        await FallingEdge(dut.clk)
        if int(dut.uart_txp.value) == 0:            # start bit
            for _ in range(BAUD_DIV + BAUD_DIV // 2):
                await RisingEdge(dut.clk)
            b = 0
            for i in range(8):
                await FallingEdge(dut.clk)
                b |= int(dut.uart_txp.value) << i
                for _ in range(BAUD_DIV):
                    await RisingEdge(dut.clk)
            sink.append(b)


async def wait_halt(dut, max_cycles):
    for _ in range(max_cycles):
        await FallingEdge(dut.clk)
        if int(dut.halted.value):
            return True
    return False


@cocotb.test()
async def hot_swap_two_isas(dut):
    holder = {'cs': dict(build_gismo())}           # Gismo only at boot
    sw, sa = strings_words()
    smem = {sa + i: w for i, w in enumerate(sw)}   # console text blob
    txbuf = []
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    dut.uart_rxp.value = 1
    dut.cs_rdata.value = HALTW
    dut.m_rdata.value = 0
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    cocotb.start_soon(cs_proc(dut, holder))
    cocotb.start_soon(smem_proc(dut, smem))
    cocotb.start_soon(tx_capture(dut, txbuf))

    # with no interpreter, address 0 is HALT: machine parks immediately
    assert await wait_halt(dut, 100), "no initial halt"

    # ---- console: '?' wakes the machine and prints the menu ----
    await send_bytes(dut, b'?')
    for _ in range(len(MENU_TEXT) * (BAUD_DIV * 12) + 20000):
        await RisingEdge(dut.clk)
        if len(txbuf) >= len(MENU_TEXT):
            break
    got = bytes(txbuf).decode('ascii', 'replace')
    txbuf.clear()
    dut._log.info(f"console said: {got!r}")
    assert got == MENU_TEXT, "menu text mismatch"

    # ---- load and run the stack machine S-language ----
    stk_prog = stk_asm([('pushb', 21), ('pushb', 34), 'add',
                        'out', 'halt'])
    stream = loader_stream(cs_image=build_stack_interpreter(),
                           mem_words=stk_prog,
                           mem_word_addr=CODE_BYTE // 4, go=True)
    dut._log.info(f"stack S-language stream: {len(stream)} bytes")
    await send_bytes(dut, stream)
    assert await wait_halt(dut, 20000), "stack machine did not halt"
    for _ in range(6000):
        await RisingEdge(dut.clk)
        if bytes(txbuf).endswith(b'\r\n'):
            break
    said = bytes(txbuf).decode('ascii', 'replace')
    txbuf.clear()
    mon = int(dut.mon.value)
    dut._log.info(f"stack machine: mon={mon}, console={said!r}")
    assert mon == 55 and said == "00000037\r\n" 

    # ---- hot swap: same bitstream, now load RV32I ----
    rv_prog = rv_asm([
        ('addi', 1, 0, 10),
        ('addi', 2, 0, 0),
        ('label', 'loop'),
        ('add', 2, 2, 1),
        ('addi', 1, 1, -1),
        ('bne', 1, 0, 'loop'),
        ('addi', 10, 2, 0),
        ('ecall',),
    ])
    stream = loader_stream(cs_image=build_interpreter(),
                           mem_words=rv_prog,
                           mem_word_addr=CODE_BYTE // 4, go=True)
    dut._log.info(f"RV32I stream: {len(stream)} bytes")
    await send_bytes(dut, stream)
    assert await wait_halt(dut, 200000), "RV32I did not halt"
    for _ in range(8000):
        await RisingEdge(dut.clk)
        if bytes(txbuf).endswith(b'\r\n'):
            break
    said = bytes(txbuf).decode('ascii', 'replace')
    txbuf.clear()
    mon = int(dut.mon.value)
    dut._log.info(f"RV32I: mon={mon}, console={said!r}")
    assert mon == 55 and said == "a0=00000037\r\n" 
    assert smem.get(2, 0) == 55 and smem.get(10, 0) == 55

    # ---- and back again: reload the stack machine ----
    stk2 = stk_asm([('pushb', 40), ('pushb', 2), 'sub', 'out', 'halt'])
    stream = loader_stream(cs_image=build_stack_interpreter(),
                           mem_words=stk2,
                           mem_word_addr=CODE_BYTE // 4, go=True)
    await send_bytes(dut, stream)
    assert await wait_halt(dut, 20000), "second stack run did not halt"
    mon = int(dut.mon.value)
    dut._log.info(f"stack machine again: mon={mon}")
    assert mon == 38
