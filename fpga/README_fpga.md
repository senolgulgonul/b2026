# b2026 FPGA build v0.3 (20260821)

## Files
- b26_fpga.v: top wrapper (core + inferred BSRAM memories + reset + LEDs)
- b26.cst / b26.sdc: Tang Nano 9K pins and the 27 MHz clock constraint
- export_ucode.py: regenerates cs_init.hex and smem_init.hex
- build_gowin.tcl: batch build for gw_sh

## Steps (Gowin EDA GUI)
1. python3 export_ucode.py .   (writes the two hex files next to the tcl)
2. New project, device GW1NR-9C, package QN88, part
   GW1NR-LV9QN88PC6/I5.
3. Add ../rtl/fnbox.v ../rtl/fiu.v ../rtl/useq.v ../rtl/b26.v
   b26_fpga.v, plus b26.cst and b26.sdc. Top module: b26_fpga.
4. Synthesize, place and route, program via openFPGALoader or the
   Gowin programmer.

$readmemh paths are relative to the synthesis working directory; keep
cs_init.hex and smem_init.hex where the tool runs (the project impl
directory if the GUI complains, or pass absolute paths in the INIT
parameters).

## Expected behavior
After power-on (about 1.2 ms POR) the interpreter boots, runs the demo
RV32I program (sum 10..1, a0 = 55), and halts with 55 on the monitor
port. LEDs are active low, so the pattern is: led[3] dark, all others
lit. Pressing S1 resets and reruns the demo.

## Console (B1700 SPO style)

Power-on and button reset now boot into the Gismo console: the board
prints a banner and a B26> prompt on UART TX (115200 8N1, FPGA pin 17).
Open any terminal (PuTTY, TeraTerm) on the same COM port:

    G        run the loaded interpreter (RV32I demo at power-on)
    ?        print the menu again (works from halt too: any byte wakes)

The binary L/M/G loader protocol is unchanged; b26_send.py works as
before and now also prints anything the console says back.

## Hot-swapping S-languages (the soft machine demo)

The control store is writable at run time. A resident microcode loader
(Gismo, at 0xE00) wakes a halted machine on the first UART byte from
the on-board USB serial bridge (115200 8N1, FPGA pin 18). To swap the
running ISA without touching the bitstream:

    pip install pyserial
    python3 b26_send.py COM5 stack      # byte-coded stack machine, LEDs 55
    python3 b26_send.py COM5 rv32i      # back to RV32I, LEDs 55 again

The default bitstream image contains Gismo plus the RV32I interpreter,
so the board boots the RV32I demo and accepts swaps afterwards. The
stack-machine interpreter is 69 microwords against RV32I's 826.

## Notes
- Control store: 4096 x 16, S-memory: 4096 x 32; both should infer to
  BSRAM (about 12 of 26 blocks). Check the synthesis report.
- Timing: 27 MHz, one long path by design (cs_rdata through condition
  mux and target adder back to the BSRAM address). If timing fails,
  report the slack; the fallback is registering the dispatch target and
  accepting a one-cycle branch bubble.
