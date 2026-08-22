# b2026 comparison pack v0.6 (20260822)

Same board, same harness, same workload: SERV, PicoRV32 and b2026
on the Tang Nano 9K (GW1NR-LV9QN88PC6/I5, 27 MHz, no PLL). Each core
gets one 4096 x 32 inferred BSRAM holding code and data, a power-on
reset, and six active-low LEDs latched by a store to byte 4092. Nothing
else is attached, so the resource numbers are the core plus a few LUTs
of glue.

## Reference workload

bench.S: sum 1..100, mask to six bits, store to the LED port. 305
executed RV32I instructions, result 5050, LEDs show 58.

## Cycle counts (Icarus, measured here)

| Core | Cycles | CPI | Notes |
| --- | --- | --- | --- |
| PicoRV32 | 1527 | 5.0 | small config, no counters, no two-stage shift |
| SERV | 14217 | 46.6 | bit-serial, WITH_CSR=0 |
| Glacial | n/a | ~953 | 8-bit microcoded, instruction-mix average (see below) |
| b2026 | 24808 | 81.3 | microcoded interpreter, writable control store |

Both wrappers use a one-wait-state memory, matching the b2026 BSRAM
timing, so the comparison is like for like. The RAM is written as plain
32-bit words with the byte lanes merged in logic, because GW1NR-9 BSRAM
does not support the write-through mode that byte enables would infer
(Gowin PA2122).

## Synthesis (to be filled in from Gowin reports)

| Core | LUT | ALU | Registers | BSRAM | Fmax (MHz) | ISA |
| --- | --- | --- | --- | --- | --- | --- |
| PicoRV32 | 1097 | 211 | 446 | 10 | 46.3 | fixed RV32I |
| SERV | 283 | 21 | 210 | 9 | 53.9 | fixed RV32I |
| Glacial | 236 | 38 | 108 | 8 | 66.7 | fixed RV32I, microcoded |
| b2026 | 2569 | 387 | 461 | 12 | 29.7 (v0.2 core) | writable, swappable at run time |

All figures are post-place-and-route on GW1NR-LV9QN88PC6/I5 with the
same wrapper, the same 4096 x 32 BSRAM and the same 27 MHz constraint;
zero setup and hold violations in every case. Critical path depth: SERV
5 levels, PicoRV32 6, b2026 15. The extra depth is the bias
mechanism itself (CPL to mask generation, the carry chain, the variable
bit select for CYL, the dispatch mux), which is also where most of the
LUT difference lives: register counts are close (446 for PicoRV32
against 461 here), so the cost of a definable machine shows up in
combinational logic, not in state.

## Getting the baseline cores

The three cores are not vendored here; fetch them at a known revision:

    ./fetch_cores.sh

This clones SERV, PicoRV32 and Glacial into third_party/, copies the
RTL into rtl/ next to our wrappers, and prints the revisions used.

## Running the syntheses

From this directory:

    gw_sh build_serv.tcl        -> serv_prj/impl/
    gw_sh build_picorv32.tcl    -> pico_prj/impl/

Each script creates its own project directory, so the two cores never
overwrite each other's reports or bitstreams. The matching init hex is
pre-placed in both the project directory and its impl/gwsynthesis
subdirectory, since $readmemh resolves against whatever directory the
tool happens to run in.

Reports to collect per core: impl/pnr/*.rpt.txt (resources) and
impl/pnr/*.tr.html (Fmax). Bitstream: impl/pnr/*.fs.

## Running the simulations

    cd sim
    iverilog -o serv.vvp ../rtl/serv_*.v tb_serv.v   # see the tcl for the file list
    vvp serv.vvp
    iverilog -o pico.vvp ../rtl/picorv32.v ../rtl/picorv32_fpga.v tb_picorv32.v
    vvp pico.vvp

b2026's number comes from tb/test_bench_cpi.py (make DUT=b26
MODULE=test_bench_cpi).

## Glacial

Glacial (brouhaha/glacial, BSD-2-Clause) is the closest published
relative: microcoded, RV32I, with microcode, scratchpad and RISC-V
memory sharing one byte-wide RAM. glacial_fpga.v wraps it for the same
board; because it needs a byte-wide address space rather than 32-bit
words, its harness is 16 KB of byte-wide BSRAM (64 KB would exceed the
GW1NR-9's 468 Kbit) with the result byte latched from a store to the
top of memory.

    gw_sh build_glacial.tcl     -> glacial_prj/impl/

The memory image (glacial_init.hex) was built with the upstream
toolchain: microcode assembled with ucode/tools/asg and merged with the
RISC-V binary by ucode/tools/vmem, which relocates the program by the
offset the microcode stores at bytes 2 and 3 (0x0A00 here).

Glacial's CPI is reported as an instruction-mix average rather than a
completed run. Using the upstream testbench's clocking and its own
instruction-retire trace point (phase 3 at microcode address 0x0f4),
the reference workload retires 10000 RISC-V instructions in 9538641
cycles, i.e. about 953 cycles per instruction. The program does not
terminate in our harness: after the fifth instruction the RISC-V PC
returns to zero, which looks like a trap taken with mtvec still zero,
so the loop restarts indefinitely. Since Glacial passes the official
compliance suite upstream, the fault is most likely in our environment
(we assembled the microcode ourselves with ucode/tools/asg, as the
repository ships no prebuilt image). We therefore report the per
instruction figure, which the instruction counter measures directly,
and not a wall-clock time for the workload. The resource figures are
from synthesis and do not depend on the program.
