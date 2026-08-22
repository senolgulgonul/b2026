#!/usr/bin/env python3
# b2026 export_ucode v0.3 (20260821)
# Emits cs_init.hex (4096 x 16, the RV32I interpreter) and smem_init.hex
# (4096 x 32, register file zeros + demo program) for $readmemh.
#
# Demo: sum 10..1, move the total into a0, ecall. The SYSTEM handler
# shows a0 on the monitor port, so the board LEDs display 55 (0x37).

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tb"))
from ucode_rv32i import (build_interpreter, build_gismo, strings_words,
                         rv_asm, ISS, CODE_BYTE)

CS_DEPTH = 4096
SM_DEPTH = 4096
HALTW = 0xF100

demo = rv_asm([
    ('addi', 1, 0, 10),
    ('addi', 2, 0, 0),
    ('label', 'loop'),
    ('add', 2, 2, 1),
    ('addi', 1, 1, -1),
    ('bne', 1, 0, 'loop'),
    ('addi', 10, 2, 0),        # a0 <- total
    ('ecall',),
])

iss = ISS(demo)
iss.run()
assert iss.x[10] == 55, iss.x[10]

prog = dict(build_interpreter())
prog.update(build_gismo())   # resident loader: halted machine wakes on UART
outdir = sys.argv[1] if len(sys.argv) > 1 else "."

with open(os.path.join(outdir, "cs_init.hex"), "w") as f:
    for a in range(CS_DEPTH):
        f.write(f"{prog.get(a, HALTW):04x}\n")

smem = {CODE_BYTE // 4 + i: w for i, w in enumerate(demo)}
sw, sa = strings_words()
smem.update({sa + i: w for i, w in enumerate(sw)})
with open(os.path.join(outdir, "smem_init.hex"), "w") as f:
    for a in range(SM_DEPTH):
        f.write(f"{smem.get(a, 0):08x}\n")

print(f"cs_init.hex: {len(prog)} used / {CS_DEPTH} words")
print(f"smem_init.hex: {len(demo)} demo words at byte {CODE_BYTE}, "
      f"expected LEDs value {iss.x[10]} (0x{iss.x[10]:02x})")
