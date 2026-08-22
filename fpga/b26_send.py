#!/usr/bin/env python3
# b2026 b26_send v0.4 (20260822)
# Host-side loader: sends an S-language (interpreter microcode plus its
# program) to the board over the USB serial bridge at 115200 8N1.
#
# Usage:
#   python3 b26_send.py COM3 stack            # stack demo: 21+34 = 55
#   python3 b26_send.py COM3 stack 5 34       # custom: 5+34 = 39
#   python3 b26_send.py COM3 stack 40 2 sub   # subtraction: 40-2 = 38
#   python3 b26_send.py COM3 rv32i            # RV32I sum loop, a0 = 55
#   python3 b26_send.py COM3 term             # interactive console
#   python3 b26_send.py COM3 rv32i 20         # sum 1..20 = 210 (mod 64
#                                             # on the six LEDs: 0b010010)
#
# A halted machine wakes into the resident Gismo loader on the first
# byte; no reset needed. Requires: pip install pyserial

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tb"))
from ucode_rv32i import (build_interpreter, build_stack_interpreter,
                         stk_asm, rv_asm, loader_stream, CODE_BYTE)


def make_stream(which, args):
    if which == "stack":
        a = int(args[0]) & 0xFF if len(args) > 0 else 21
        b = int(args[1]) & 0xFF if len(args) > 1 else 34
        op = args[2] if len(args) > 2 else 'add'
        if op not in ('add', 'sub'):
            raise SystemExit("stack op must be add or sub")
        result = (a + b if op == 'add' else a - b) & 0xFF
        prog = stk_asm([('pushb', a), ('pushb', b), op, 'out', 'halt'])
        return loader_stream(cs_image=build_stack_interpreter(),
                             mem_words=prog,
                             mem_word_addr=CODE_BYTE // 4,
                             go=True), result
    if which == "rv32i":
        n = int(args[0]) if args else 10
        prog = rv_asm([
            ('addi', 1, 0, n),
            ('addi', 2, 0, 0),
            ('label', 'loop'),
            ('add', 2, 2, 1),
            ('addi', 1, 1, -1),
            ('bne', 1, 0, 'loop'),
            ('addi', 10, 2, 0),
            ('ecall',),
        ])
        return loader_stream(cs_image=build_interpreter(),
                             mem_words=prog,
                             mem_word_addr=CODE_BYTE // 4,
                             go=True), (n * (n + 1) // 2) & 0xFF
    raise SystemExit(f"unknown image '{which}' (use: stack | rv32i)")


def term(port):
    # line-based console: type G or ?, 'exit' quits
    import threading
    import serial
    with serial.Serial(port, 115200, timeout=0.2) as s:
        stop = []

        def reader():
            while not stop:
                d = s.read(256)
                if d:
                    sys.stdout.write(d.decode('ascii', 'replace'))
                    sys.stdout.flush()
        th = threading.Thread(target=reader, daemon=True)
        th.start()
        print("[term] connected; type G, ?, or exit")
        try:
            while True:
                line = input()
                if line.strip().lower() == 'exit':
                    break
                s.write(line.encode('ascii', 'replace'))
        finally:
            stop.append(1)


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    port, which = sys.argv[1], sys.argv[2]
    if which == 'term':
        return term(port)
    stream, result = make_stream(which, sys.argv[3:])
    print(f"{which}: {len(stream)} bytes, expected result {result} "
          f"(LEDs show ~{result & 0x3F:06b}, 0 = lit)")
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
