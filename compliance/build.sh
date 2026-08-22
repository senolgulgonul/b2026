#!/bin/bash
# b2026 compliance build v0.1 (20260821)
set -e
SRC=/home/claude/riscv-tests/isa/rv32ui
MAC=/home/claude/riscv-tests/isa/macros/scalar
OUT=bins
mkdir -p $OUT
ok=0; skip=0
for s in $SRC/*.S; do
  n=$(basename $s .S)
  if riscv64-unknown-elf-gcc -march=rv32i_zifencei -mabi=ilp32 -static \
      -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles \
      -I. -I$MAC -T link.ld $s -o $OUT/$n.elf 2> $OUT/$n.err; then
    riscv64-unknown-elf-objcopy -O binary $OUT/$n.elf $OUT/$n.bin
    ok=$((ok+1))
  else
    skip=$((skip+1)); echo "SKIP $n: $(head -1 $OUT/$n.err)"
  fi
done
echo "built $ok, skipped $skip"
