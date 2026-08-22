# B2026

A soft machine for the Tang Nano 9K, named in homage to the Burroughs
B1700 and built on its principles (Wilner, 1972): the hardware
implements no instruction set. Memory is addressed to the bit, an
operand-length register reshapes the arithmetic unit every cycle, and
the control store is writable at run time, so an instruction set is
data rather than a synthesis artifact.

RV32I is one S-language, written in 838 microwords, passing the
official riscv-tests rv32ui suite 42 of 42 including misaligned access.
A byte-coded stack machine is another, in 75 microwords. Both run on
the same bitstream and are exchanged over the serial line in about a
second.

    B26> G
    a0=00000037

## What is here

    rtl/         fnbox, fiu, useq, b26, uart_rx, uart_tx
    tb/          cocotb suites: unit, ISS-compared RV32I, compliance,
                 loader and console, L/M loader exercises
    fpga/        Tang Nano 9K wrapper, constraints, Gowin build script,
                 microcode image export, host-side console tools
    compliance/  minimal riscv-tests environment and build script
    compare/     same-board comparison against SERV, PicoRV32, Glacial
    doc/         architecture specification

## Quick start, simulation

Needs Icarus Verilog and cocotb.

    cd tb
    make DUT=fnbox           # unit suites: fnbox, fiu, useq, b26
    make DUT=b26 MODULE=test_rv32i        # RV32I against a golden ISS
    make DUT=b26 MODULE=test_loader       # two S-languages, hot swap
    make DUT=b26 MODULE=test_compliance   # rv32ui, 42 tests

The compliance suite needs the test binaries first:

    cd compliance && ./build.sh           # needs riscv64-unknown-elf-gcc

## Quick start, hardware

    cd fpga
    python3 export_ucode.py .             # writes cs_init.hex, smem_init.hex
    gw_sh build_gowin.tcl                 # Gowin EDA V1.9.12

Program the bitstream, then open the console at 115200 8N1:

    python3 b26_send.py COM3 term         # banner, G runs, ? prints the menu
    python3 b26_send.py COM3 stack 7 8    # load the stack machine, prints 0000000F
    python3 b26_send.py COM3 rv32i 20     # load RV32I, prints a0=000000D2
    python3 b26_lmtest.py COM3 l 42       # six microwords, no interpreter at all

## Comparison

`compare/` builds SERV, PicoRV32 and Glacial for the same board with
the same wrapper and workload. The baseline cores are not vendored:

    cd compare && ./fetch_cores.sh
    gw_sh build_serv.tcl
    gw_sh build_picorv32.tcl
    gw_sh build_glacial.tcl

Measured on GW1NR-LV9QN88PC6/I5, 27 MHz, zero timing violations:

| Core | LUT | FF | BSRAM | Fmax (MHz) | CPI | Instruction set |
| --- | --- | --- | --- | --- | --- | --- |
| Glacial | 236 | 108 | 8 | 66.7 | ~953 | fixed |
| SERV | 283 | 210 | 9 | 53.9 | 46.6 | fixed |
| PicoRV32 | 1097 | 446 | 10 | 46.3 | 5.0 | fixed |
| B2026 | 2569 | 461 | 12 | 29.7 | 81.3 | writable, swappable |

On every axis a fixed-ISA core is optimized for, this design loses.
The column the table does not have is the one being paid for. See
`compare/README_compare.md` for the method and the caveats, including
why Glacial's CPI is an instruction-mix average.

## Licence

MIT, see LICENSE. The baseline cores fetched into `compare/rtl` keep
their own licences: SERV and PicoRV32 are ISC, Glacial is BSD-2-Clause.

## Reference

W. T. Wilner, *B1700 Design and Implementation*, Burroughs Corporation,
Santa Barbara Plant, May 1972.
