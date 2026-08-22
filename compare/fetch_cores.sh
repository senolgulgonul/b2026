#!/bin/bash
# b2026 compare fetch_cores v0.1 (20260822)
# Fetches the three baseline cores. They are not vendored here: each
# carries its own licence (SERV ISC, PicoRV32 ISC, Glacial BSD-2) and
# is better taken from its own repository at a known revision.
set -e
cd "$(dirname "$0")"
mkdir -p third_party rtl
cd third_party
[ -d serv ]     || git clone --depth 1 https://github.com/olofk/serv.git
[ -d picorv32 ] || git clone --depth 1 https://github.com/YosysHQ/picorv32.git
[ -d glacial ]  || git clone --depth 1 https://github.com/brouhaha/glacial.git
cd ..
cp third_party/serv/rtl/serv_*.v rtl/
cp third_party/picorv32/picorv32.v rtl/
cp third_party/glacial/verilog/glacial.v third_party/glacial/verilog/sram.v rtl/
echo "cores fetched into rtl/ (wrappers *_fpga.v are ours and stay in git)"
echo
echo "record the revisions used in a paper:"
for d in serv picorv32 glacial; do
  printf '%-10s %s\n' "$d" "$(git -C third_party/$d rev-parse --short HEAD)"
done
