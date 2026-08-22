#!/usr/bin/env python3
# b2026 b26_lmtest v0.2 (20260822)
# Teaching-sized exercises for the Gismo L and M loader commands.
#
#   python3 b26_lmtest.py COM3 l 42
#       L only: loads a three-microword program at address 0
#       (LIT 42; MONR; HALT) and runs it. The LEDs show 42 with no
#       interpreter involved at all: bare microcode.
#
#   python3 b26_lmtest.py COM3 m 33
#       L + M: loads a five-microword "peek" program that reads one
#       byte from S-memory word 500 and shows it, then M-writes your
#       value into that word. Change the value, resend, and only the
#       M block differs: the data travels through memory, not code.
#
# Values 0..63 map directly onto the six LEDs (0 bit = lit LED).

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tb"))
from ucode_rv32i import (LIT, LITS, MOVE, RD, MONR, HALT, RT, SFA, C_T,
                         SVC_PUTC, SVC_PUTHEX, loader_stream)

PEEK_WORD = 500                      # S-memory word the 'm' test reads
PEEK_BITS = PEEK_WORD * 32


def _crlf_halt(base):
    return {base: LIT(13), base + 1: 0x8000 | SVC_PUTC,
            base + 2: LIT(10), base + 3: 0x8000 | SVC_PUTC,
            base + 4: HALT()}


def prog_l(value):
    # LIT value; MONR; S10 <- T; print hex via the Gismo service; HALT
    p = {0: LIT(value & 0xFF), 1: MONR(), 2: MOVE(RT, 10),
         3: 0x8000 | SVC_PUTHEX}
    p.update(_crlf_halt(4))
    return p


def prog_m():
    # SF.A <- PEEK_BITS; T <- 8 bits at SF.A; MONR; print hex; HALT
    p = {0: LIT(PEEK_BITS >> 12), 1: LITS(PEEK_BITS),
         2: MOVE(RT, SFA), 3: RD(C_T, sf=1, ln=8),
         4: MONR(), 5: MOVE(RT, 10), 6: 0x8000 | SVC_PUTHEX}
    p.update(_crlf_halt(7))
    return p


def make_stream(mode, value):
    if mode == 'l':
        return loader_stream(cs_image=prog_l(value), go=True)
    if mode == 'm':
        return loader_stream(cs_image=prog_m(),
                             mem_words=[value & 0xFF],
                             mem_word_addr=PEEK_WORD, go=True)
    raise SystemExit("mode must be l or m")


def main():
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    port, mode, value = sys.argv[1], sys.argv[2], int(sys.argv[3])
    stream = make_stream(mode, value)
    print(f"{mode}: {len(stream)} bytes, expect LEDs "
          f"{value & 0x3F:06b} (0 = lit)")
    import serial
    with serial.Serial(port, 115200, timeout=0.3) as s:
        time.sleep(0.1)
        s.write(stream)
        s.flush()
        echo = s.read(4096)
    print("sent")
    if echo:
        print("console:", echo.decode('ascii', 'replace'))


if __name__ == "__main__":
    main()
