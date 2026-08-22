# b2026 ucode_rv32i v0.7 (20260821)
# Full RV32I interpreter as microcode, plus a small RISC-V assembler and a
# golden ISS for verification.
#
# Control store layout:
#   0x000..      boot + fetch/dispatch
#   0x100+op     major opcode table (page 1)
#   0x200+f3     BRANCH funct3 table (page 2)
#   0x300+f3     LOAD funct3 table (page 3)
#   0x400+f3     STORE funct3 table (page 4)
#   0x500+f3     OP-IMM funct3 table (page 5)
#   0x600+f3     OP funct3 table (page 6)
#   0x700..      handlers and subroutines

M32 = 0xFFFFFFFF
CODE_BITS = 2048          # RV32I code at byte 256
CODE_BYTE = CODE_BITS // 8

# ---------- register names ----------
RX, RY, RT = 0x10, 0x11, 0x12
FA_, FL_, SFA, SFL, RCPL = 0x13, 0x14, 0x15, 0x16, 0x17
SUM, DIFF, ANDR, ORR, XORR, MSKX, ZERO, ONES = (
    0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F)
C_X, C_Y, C_T = 12, 13, 14
Z, NZ, CYL, NCYL, N, NN, FL0, FLNZ = 0, 1, 2, 3, 4, 5, 6, 7

# ---------- microinstruction encoders ----------
def MOVE(src, dst):  return 0x0000 | (src << 6) | dst
def LIT(v):          return 0x1000 | (v & 0xFFF)
def LITS(v):         return 0x2000 | (v & 0xFFF)
def RD(d4, sf=0, cnt=0, ln=0):
    return 0x3000 | (d4 << 8) | (sf << 7) | (cnt << 5) | (ln & 0x1F)
def WR(s4, sf=0, cnt=0, ln=0):
    return 0x4000 | (s4 << 8) | (sf << 7) | (cnt << 5) | (ln & 0x1F)
def EXTI(pos):       return 0x5000 | ((pos & 0x3F) << 6)
def DISP(page):      return 0xA000 | ((page & 0xF) << 8)
def BIASL(n):        return 0xB000 | (n & 0x3F)
def CNT(desc, op, ksel, k):
    return 0xC000 | (desc << 11) | (op << 9) | (ksel << 8) | (k & 0xFF)
URX, UTX = 0x20, 0x21
COND_TXB = 12
def MON(v):          return 0xF200 | (v & 0xFF)
def URXACK():        return 0xF400
def CSW():           return 0xF500
def MONR():          return 0xF300
def HALT():          return 0xF100

# ---------- two-pass microassembler ----------
def asm(items):
    addr, labels, seq = 0, {}, []
    for it in items:
        if isinstance(it, tuple) and it[0] == 'L':
            labels[it[1]] = addr
        elif isinstance(it, tuple) and it[0] == 'ORG':
            addr = it[1]
        else:
            seq.append((addr, it))
            addr += 1
    prog = {}
    for a, it in seq:
        assert a < 0x1000, "control store overflow"
        assert a not in prog, f"address collision at {a:#x}"
        if isinstance(it, int):
            prog[a] = it
        elif it[0] == 'BR':
            prog[a] = 0x6000 | ((labels[it[1]] - a) & 0xFFF)
        elif it[0] == 'IF':
            off = labels[it[2]] - a
            assert -128 <= off < 128, f"IF range to {it[2]}"
            prog[a] = 0x7000 | (it[1] << 8) | (off & 0xFF)
        elif it[0] == 'CALL':
            t = it[1]
            prog[a] = 0x8000 | (t if isinstance(t, int) else labels[t])
        elif it[0] == 'EXIT':
            prog[a] = 0x9000
        else:
            raise ValueError(it)
    return prog

# ---------- microcode macros ----------
def lit32(v):
    v &= M32
    if v < (1 << 12):
        return [LIT(v)]
    if v < (1 << 24):
        return [LIT(v >> 12), LITS(v)]
    return [LIT(v >> 24), LITS(v >> 12), LITS(v)]

def m_setmask():
    return [LIT(0x3E0), MOVE(RT, RY)]

def m_rd_addr(pos, dst6):
    # dst <- regnum*32, regnum at inst[pos+9:pos+5]; needs Y=0x3E0
    return [MOVE(13, RX), BIASL(10), EXTI(pos),
            MOVE(RT, RX), MOVE(ANDR, dst6)]

def m_load_reg(pos, d4):
    return m_rd_addr(pos, SFA) + [BIASL(32), RD(d4, sf=1)]

def m_extract(pos, ln):
    return [MOVE(13, RX), BIASL(ln), EXTI(pos), BIASL(32)]

def m_sext_T(n):
    m = 1 << (n - 1)
    return [MOVE(RT, RX)] + lit32(m) + [MOVE(RT, RY),
                                        MOVE(XORR, RX), MOVE(DIFF, RX)]

def m_double():
    return [MOVE(RX, RY), MOVE(SUM, RX)]

def m_horner(pos, ln, k, park=10):
    return ([MOVE(RX, park)] + m_extract(pos, ln) + [MOVE(park, RX)]
            + k * m_double() + [MOVE(RT, RY), MOVE(SUM, RX)])

def m_setbool(lbl):
    # S10 <- 1 if CYL else 0
    return [('IF', CYL, lbl + '_1'), LIT(0), ('BR', lbl + '_s'),
            ('L', lbl + '_1'), LIT(1), ('L', lbl + '_s'), MOVE(RT, 10)]

# ---------- the interpreter ----------
def build_interpreter():
    mc = []
    mc += [('ORG', 0)] + lit32(CODE_BITS) + [MOVE(RT, 15), ('BR', 'fetch')]
    mc += [('L', 'fetch'),
           MOVE(15, FA_), MOVE(15, 14),
           BIASL(32), RD(C_X, cnt=3),
           MOVE(FA_, 15), MOVE(RX, 13),
           BIASL(7), EXTI(0), DISP(1)]

    # ---- dispatch tables ----
    mc += [('ORG', 0x100 + 0x03), ('BR', 'h_load'),
           ('ORG', 0x100 + 0x0F), ('BR', 'h_fence'),
           ('ORG', 0x100 + 0x13), ('BR', 'h_opimm'),
           ('ORG', 0x100 + 0x17), ('BR', 'h_auipc'),
           ('ORG', 0x100 + 0x23), ('BR', 'h_store'),
           ('ORG', 0x100 + 0x33), ('BR', 'h_op'),
           ('ORG', 0x100 + 0x37), ('BR', 'h_lui'),
           ('ORG', 0x100 + 0x63), ('BR', 'h_branch'),
           ('ORG', 0x100 + 0x67), ('BR', 'h_jalr'),
           ('ORG', 0x100 + 0x6F), ('BR', 'h_jal'),
           ('ORG', 0x100 + 0x73), ('BR', 'h_sys')]
    mc += [('ORG', 0x200 + 0), ('BR', 'b_eq'),
           ('ORG', 0x200 + 1), ('BR', 'b_ne'),
           ('ORG', 0x200 + 4), ('BR', 'b_lt'),
           ('ORG', 0x200 + 5), ('BR', 'b_ge'),
           ('ORG', 0x200 + 6), ('BR', 'b_ltu'),
           ('ORG', 0x200 + 7), ('BR', 'b_geu')]
    mc += [('ORG', 0x300 + 0), ('BR', 'l_b'),
           ('ORG', 0x300 + 1), ('BR', 'l_h'),
           ('ORG', 0x300 + 2), ('BR', 'l_w'),
           ('ORG', 0x300 + 4), ('BR', 'l_bu'),
           ('ORG', 0x300 + 5), ('BR', 'l_hu')]
    mc += [('ORG', 0x400 + 0), ('BR', 's_b'),
           ('ORG', 0x400 + 1), ('BR', 's_h'),
           ('ORG', 0x400 + 2), ('BR', 's_w')]
    mc += [('ORG', 0x500 + 0), ('BR', 'i_addi'),
           ('ORG', 0x500 + 1), ('BR', 'i_slli'),
           ('ORG', 0x500 + 2), ('BR', 'i_slti'),
           ('ORG', 0x500 + 3), ('BR', 'i_sltiu'),
           ('ORG', 0x500 + 4), ('BR', 'i_xori'),
           ('ORG', 0x500 + 5), ('BR', 'i_srxi'),
           ('ORG', 0x500 + 6), ('BR', 'i_ori'),
           ('ORG', 0x500 + 7), ('BR', 'i_andi')]
    mc += [('ORG', 0x600 + 0), ('BR', 'o_addsub'),
           ('ORG', 0x600 + 1), ('BR', 'o_sll'),
           ('ORG', 0x600 + 2), ('BR', 'o_slt'),
           ('ORG', 0x600 + 3), ('BR', 'o_sltu'),
           ('ORG', 0x600 + 4), ('BR', 'o_xor'),
           ('ORG', 0x600 + 5), ('BR', 'o_srx'),
           ('ORG', 0x600 + 6), ('BR', 'o_or'),
           ('ORG', 0x600 + 7), ('BR', 'o_and')]

    mc += [('ORG', 0x700)]

    # ---- subroutines ----
    # writeback: if rd != 0 (rd*32 in S12): x[rd] <- S10
    mc += [('L', 'sub_wb'),
           MOVE(12, RX), LIT(0), MOVE(RT, RY), ('IF', Z, 'wb_skip'),
           MOVE(12, SFA), BIASL(32), WR(10, sf=1),
           ('L', 'wb_skip'), ('EXIT',)]
    # unsigned compare: after return, CYL <=> S11 <u S10
    mc += [('L', 'sub_ltu'),
           MOVE(11, RX), MOVE(ONES, RY), MOVE(XORR, RX),
           MOVE(10, RY), ('EXIT',)]
    # flip sign bits of S11 and S10 (signed compare prep)
    mc += [('L', 'sub_flip')] + lit32(0x80000000) + [
           MOVE(RT, RY), MOVE(11, RX), MOVE(XORR, 11),
           MOVE(10, RX), MOVE(XORR, 10), ('EXIT',)]
    # shift left: X <<= F.L
    mc += [('L', 'sub_sll'), ('IF', FL0, 'sll_done'),
           ('L', 'sll_loop'), MOVE(RX, RY), MOVE(SUM, RX),
           CNT(0, 2, 1, 1), ('IF', FLNZ, 'sll_loop'),
           ('L', 'sll_done'), ('EXIT',)]
    # shift right logical: X >>= F.L
    mc += [('L', 'sub_srl'), ('IF', FL0, 'srl_done'),
           ('L', 'srl_loop'), EXTI(1), MOVE(RT, RX),
           CNT(0, 2, 1, 1), ('IF', FLNZ, 'srl_loop'),
           ('L', 'srl_done'), ('EXIT',)]
    # shift right arithmetic: X >>= F.L, sign held in S8
    mc += [('L', 'sub_sra')] + lit32(0x80000000) + [
           MOVE(RT, 8), ('IF', FL0, 'sra_done'),
           ('L', 'sra_loop'), EXTI(1), MOVE(8, RY), MOVE(ANDR, 9),
           MOVE(RT, RX), MOVE(9, RY), MOVE(ORR, RX),
           CNT(0, 2, 1, 1), ('IF', FLNZ, 'sra_loop'),
           ('L', 'sra_done'), ('EXIT',)]

    # ---- LUI / AUIPC ----
    mc += [('L', 'h_lui')] + m_setmask() + m_rd_addr(2, 12)
    mc += m_extract(12, 20) + [MOVE(RT, RX)] + 12 * m_double()
    mc += [MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]

    mc += [('L', 'h_auipc')] + m_setmask() + m_rd_addr(2, 12)
    mc += m_extract(12, 20) + [MOVE(RT, RX)] + 12 * m_double()
    mc += [MOVE(RX, 10), MOVE(14, RX), EXTI(3), MOVE(RT, RY),
           MOVE(10, RX), MOVE(SUM, 10),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]

    # ---- JAL / JALR ----
    mc += [('L', 'h_jal')] + m_setmask() + m_rd_addr(2, 12)
    mc += [MOVE(15, RX), EXTI(3), MOVE(RT, 10), ('CALL', 'sub_wb')]
    mc += m_extract(31, 1) + [MOVE(RT, RX)]      # imm[20]
    mc += m_horner(12, 8, 8)                     # imm[19:12]
    mc += m_horner(20, 1, 1)                     # imm[11]
    mc += m_horner(21, 10, 10)                   # imm[10:1]
    mc += m_double()                             # << 1
    mc += lit32(1 << 20) + [MOVE(RT, RY), MOVE(XORR, RX), MOVE(DIFF, RX)]
    mc += 3 * m_double()
    mc += [MOVE(14, RY), MOVE(SUM, 15), ('BR', 'fetch')]

    mc += [('L', 'h_jalr')] + m_setmask() + m_rd_addr(2, 12)
    mc += m_load_reg(10, 11)                     # S11 <- rs1 (old value)
    mc += [MOVE(15, RX), EXTI(3), MOVE(RT, 10), ('CALL', 'sub_wb')]
    mc += m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(11, RY), MOVE(SUM, RX)]          # byte target
    mc += lit32(0xFFFFFFFE) + [MOVE(RT, RY), MOVE(ANDR, RX)]
    mc += 3 * m_double() + [MOVE(RX, 15), ('BR', 'fetch')]

    # ---- BRANCH ----
    mc += [('L', 'h_branch')] + m_setmask()
    mc += m_load_reg(10, 11) + m_load_reg(15, 10)
    mc += m_extract(12, 3) + [DISP(2)]
    mc += [('L', 'b_eq'),
           LIT(0), MOVE(RT, RX), MOVE(10, RY), MOVE(DIFF, RY),
           MOVE(11, RX), ('IF', Z, 'br_take'), ('BR', 'fetch')]
    mc += [('L', 'b_ne'),
           LIT(0), MOVE(RT, RX), MOVE(10, RY), MOVE(DIFF, RY),
           MOVE(11, RX), ('IF', NZ, 'br_take'), ('BR', 'fetch')]
    mc += [('L', 'b_ltu'), ('CALL', 'sub_ltu'),
           ('IF', CYL, 'br_take'), ('BR', 'fetch')]
    mc += [('L', 'b_geu'), ('CALL', 'sub_ltu'),
           ('IF', NCYL, 'br_take'), ('BR', 'fetch')]
    mc += [('L', 'b_lt'), ('CALL', 'sub_flip'), ('CALL', 'sub_ltu'),
           ('IF', CYL, 'br_take'), ('BR', 'fetch')]
    mc += [('L', 'b_ge'), ('CALL', 'sub_flip'), ('CALL', 'sub_ltu'),
           ('IF', NCYL, 'br_take'), ('BR', 'fetch')]
    mc += [('L', 'br_take')]
    mc += m_extract(31, 1) + [MOVE(RT, RX)]
    mc += m_horner(7, 1, 1)
    mc += m_horner(25, 6, 6)
    mc += m_horner(8, 4, 4)
    mc += m_double()
    mc += lit32(1 << 12) + [MOVE(RT, RY), MOVE(XORR, RX), MOVE(DIFF, RX)]
    mc += 3 * m_double()
    mc += [MOVE(14, RY), MOVE(SUM, 15), ('BR', 'fetch')]

    # ---- LOAD ----
    mc += [('L', 'h_load')] + m_setmask() + m_rd_addr(2, 12)
    mc += m_load_reg(10, 11)
    mc += m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(11, RY), MOVE(SUM, RX)] + 3 * m_double()
    mc += [MOVE(RX, SFA)] + m_extract(12, 3) + [DISP(3)]
    mc += [('L', 'l_w'), BIASL(32), RD(10, sf=1),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'l_bu'), BIASL(8), RD(10, sf=1),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'l_hu'), BIASL(16), RD(10, sf=1),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'l_b'), BIASL(8), RD(C_T, sf=1), BIASL(32)]
    mc += m_sext_T(8) + [MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'l_h'), BIASL(16), RD(C_T, sf=1), BIASL(32)]
    mc += m_sext_T(16) + [MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]

    # ---- STORE ----
    mc += [('L', 'h_store')] + m_setmask()
    mc += m_load_reg(10, 11) + m_load_reg(15, 10)
    mc += m_extract(25, 7) + [MOVE(RT, RX)]
    mc += m_horner(7, 5, 5, park=9)
    mc += lit32(1 << 11) + [MOVE(RT, RY), MOVE(XORR, RX), MOVE(DIFF, RX)]
    mc += [MOVE(11, RY), MOVE(SUM, RX)] + 3 * m_double()
    mc += [MOVE(RX, SFA)] + m_extract(12, 3) + [DISP(4)]
    mc += [('L', 's_b'), WR(10, sf=1, ln=8), ('BR', 'fetch')]
    mc += [('L', 's_h'), WR(10, sf=1, ln=16), ('BR', 'fetch')]
    mc += [('L', 's_w'), BIASL(32), WR(10, sf=1), ('BR', 'fetch')]

    # ---- OP-IMM ----
    mc += [('L', 'h_opimm')] + m_setmask() + m_rd_addr(2, 12)
    mc += m_load_reg(10, 11)
    mc += m_extract(12, 3) + [DISP(5)]
    mc += [('L', 'i_addi')] + m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(11, RY), MOVE(SUM, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_xori')] + m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(11, RY), MOVE(XORR, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_ori')] + m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(11, RY), MOVE(ORR, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_andi')] + m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(11, RY), MOVE(ANDR, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_slti')] + m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(RX, 10), ('CALL', 'sub_flip'), ('CALL', 'sub_ltu')]
    mc += m_setbool('sti') + [('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_sltiu')] + m_extract(20, 12) + m_sext_T(12)
    mc += [MOVE(RX, 10), ('CALL', 'sub_ltu')]
    mc += m_setbool('stiu') + [('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_slli')] + m_extract(20, 5) + [MOVE(RT, FL_),
           MOVE(11, RX), ('CALL', 'sub_sll'),
           MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'i_srxi')] + m_extract(30, 1) + [MOVE(RT, 9)]
    mc += m_extract(20, 5) + [MOVE(RT, FL_),
           MOVE(9, RX), LIT(0), MOVE(RT, RY),
           ('IF', Z, 'i_srl_'),
           MOVE(11, RX), ('CALL', 'sub_sra'), ('BR', 'i_srx_wb'),
           ('L', 'i_srl_'), MOVE(11, RX), ('CALL', 'sub_srl'),
           ('L', 'i_srx_wb'),
           MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]

    # ---- OP ----
    mc += [('L', 'h_op')] + m_setmask() + m_rd_addr(2, 12)
    mc += m_load_reg(10, 11) + m_load_reg(15, 10)
    mc += m_extract(12, 3) + [DISP(6)]
    mc += [('L', 'o_addsub')] + m_extract(30, 1) + [
           MOVE(RT, RX), LIT(0), MOVE(RT, RY), ('IF', Z, 'o_add_'),
           MOVE(11, RX), MOVE(10, RY), MOVE(DIFF, 10), ('BR', 'o_as_wb'),
           ('L', 'o_add_'), MOVE(11, RX), MOVE(10, RY), MOVE(SUM, 10),
           ('L', 'o_as_wb'), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_xor'), MOVE(11, RX), MOVE(10, RY), MOVE(XORR, 10),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_or'), MOVE(11, RX), MOVE(10, RY), MOVE(ORR, 10),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_and'), MOVE(11, RX), MOVE(10, RY), MOVE(ANDR, 10),
           ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_slt'), ('CALL', 'sub_flip'), ('CALL', 'sub_ltu')]
    mc += m_setbool('ost') + [('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_sltu'), ('CALL', 'sub_ltu')]
    mc += m_setbool('ostu') + [('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_sll'), MOVE(10, RX), BIASL(5), EXTI(0), BIASL(32),
           MOVE(RT, FL_), MOVE(11, RX), ('CALL', 'sub_sll'),
           MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]
    mc += [('L', 'o_srx')] + m_extract(30, 1) + [MOVE(RT, 9),
           MOVE(10, RX), BIASL(5), EXTI(0), BIASL(32), MOVE(RT, FL_),
           MOVE(9, RX), LIT(0), MOVE(RT, RY),
           ('IF', Z, 'o_srl_'),
           MOVE(11, RX), ('CALL', 'sub_sra'), ('BR', 'o_srx_wb'),
           ('L', 'o_srl_'), MOVE(11, RX), ('CALL', 'sub_srl'),
           ('L', 'o_srx_wb'),
           MOVE(RX, 10), ('CALL', 'sub_wb'), ('BR', 'fetch')]

    # ---- FENCE / SYSTEM ----
    mc += [('L', 'h_fence'), ('BR', 'fetch')]
    # SYSTEM: a0 (x10, bit 320) to the monitor port and, MCP style,
    # to the console via the resident Gismo services: "a0=XXXXXXXX"
    mc += [('L', 'h_sys'), LIT(320), MOVE(RT, SFA), BIASL(32),
           RD(C_T, sf=1), MONR(), MOVE(RT, 10),
           LIT(ord('a')), ('CALL', SVC_PUTC),
           LIT(ord('0')), ('CALL', SVC_PUTC),
           LIT(ord('=')), ('CALL', SVC_PUTC),
           ('CALL', SVC_PUTHEX),
           LIT(13), ('CALL', SVC_PUTC),
           LIT(10), ('CALL', SVC_PUTC), HALT()]

    return asm(mc)

# ---------- RV32I assembler ----------
def _sx(v, b):
    m = 1 << (b - 1)
    return (v & (m - 1)) - (v & m)

def rv_asm(items, base=CODE_BYTE):
    addr, labels, seq = base, {}, []
    for it in items:
        if it[0] == 'label':
            labels[it[1]] = addr
        else:
            seq.append((addr, it))
            addr += 4
    words = []
    for a, it in seq:
        mn, ar = it[0], it[1:]
        def off(t):
            return (labels[t] - a) if isinstance(t, str) else t
        R = {'add': 0x000, 'sub': 0x400, 'sll': 0x001, 'slt': 0x002,
             'sltu': 0x003, 'xor': 0x004, 'srl': 0x005, 'sra': 0x405,
             'or': 0x006, 'and': 0x007}
        I = {'addi': 0, 'slti': 2, 'sltiu': 3, 'xori': 4, 'ori': 6,
             'andi': 7, 'lb': (0x03, 0), 'lh': (0x03, 1), 'lw': (0x03, 2),
             'lbu': (0x03, 4), 'lhu': (0x03, 5), 'jalr': (0x67, 0)}
        B = {'beq': 0, 'bne': 1, 'blt': 4, 'bge': 5, 'bltu': 6, 'bgeu': 7}
        S = {'sb': 0, 'sh': 1, 'sw': 2}
        if mn in R:
            rd, rs1, rs2 = ar
            f7f3 = R[mn]
            f7bit = 1 << 30 if (f7f3 & 0x400) else 0
            w = f7bit | (rs2 << 20) | (rs1 << 15) \
                | ((f7f3 & 7) << 12) | (rd << 7) | 0x33
        elif mn in ('slli', 'srli', 'srai'):
            rd, rs1, sh = ar
            f7 = 0x20 if mn == 'srai' else 0
            f3 = 1 if mn == 'slli' else 5
            w = (f7 << 25) | (sh << 20) | (rs1 << 15) | (f3 << 12) \
                | (rd << 7) | 0x13
        elif mn in I:
            rd, rs1, imm = ar
            spec = I[mn]
            opc, f3 = (0x13, spec) if isinstance(spec, int) else spec
            w = ((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) \
                | (rd << 7) | opc
        elif mn in B:
            rs1, rs2, t = ar
            o = off(t)
            w = ((((o >> 12) & 1) << 31) | (((o >> 5) & 0x3F) << 25)
                 | (rs2 << 20) | (rs1 << 15) | (B[mn] << 12)
                 | (((o >> 1) & 0xF) << 8) | (((o >> 11) & 1) << 7) | 0x63)
        elif mn in S:
            rs2, imm, rs1 = ar
            w = (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) \
                | (S[mn] << 12) | ((imm & 0x1F) << 7) | 0x23
        elif mn == 'lui':
            rd, imm = ar
            w = ((imm & 0xFFFFF) << 12) | (rd << 7) | 0x37
        elif mn == 'auipc':
            rd, imm = ar
            w = ((imm & 0xFFFFF) << 12) | (rd << 7) | 0x17
        elif mn == 'jal':
            rd, t = ar
            o = off(t)
            w = ((((o >> 20) & 1) << 31) | (((o >> 1) & 0x3FF) << 21)
                 | (((o >> 11) & 1) << 20) | (((o >> 12) & 0xFF) << 12)
                 | (rd << 7) | 0x6F)
        elif mn == 'ecall':
            w = 0x00000073
        else:
            raise ValueError(mn)
        words.append(w)
    return words

# ---------- golden ISS ----------
class ISS:
    def __init__(self, code_words, base=CODE_BYTE):
        self.mem = {base // 4 + i: w for i, w in enumerate(code_words)}
        self.x = [0] * 32
        self.pc = base
        self.halted = False

    def _lb(self, a):
        return (self.mem.get(a >> 2, 0) >> ((a & 3) * 8)) & 0xFF

    def _sb(self, a, v):
        w, sh = a >> 2, (a & 3) * 8
        old = self.mem.get(w, 0)
        self.mem[w] = (old & ~(0xFF << sh) | ((v & 0xFF) << sh)) & M32

    def load(self, a, size, signed):
        v = 0
        for i in range(size):
            v |= self._lb(a + i) << (8 * i)
        if signed:
            v = _sx(v, 8 * size)
        return v & M32

    def store(self, a, size, v):
        for i in range(size):
            self._sb(a + i, (v >> (8 * i)) & 0xFF)

    def step(self):
        w = self.mem.get(self.pc >> 2, 0)
        op, rd = w & 0x7F, (w >> 7) & 0x1F
        f3, rs1, rs2 = (w >> 12) & 7, (w >> 15) & 0x1F, (w >> 20) & 0x1F
        f7 = w >> 25
        a, b = self.x[rs1], self.x[rs2]
        sa, sb = _sx(a, 32), _sx(b, 32)
        imm_i = _sx(w >> 20, 12)
        npc, res = self.pc + 4, None
        if op == 0x37:
            res = w & 0xFFFFF000
        elif op == 0x17:
            res = (self.pc + (w & 0xFFFFF000)) & M32
        elif op == 0x6F:
            o = (((w >> 31) & 1) << 20) | (((w >> 12) & 0xFF) << 12) \
                | (((w >> 20) & 1) << 11) | (((w >> 21) & 0x3FF) << 1)
            res, npc = (self.pc + 4) & M32, (self.pc + _sx(o, 21)) & M32
        elif op == 0x67:
            res, npc = (self.pc + 4) & M32, (a + imm_i) & M32 & ~1
        elif op == 0x63:
            o = (((w >> 31) & 1) << 12) | (((w >> 7) & 1) << 11) \
                | (((w >> 25) & 0x3F) << 5) | (((w >> 8) & 0xF) << 1)
            taken = {0: a == b, 1: a != b, 4: sa < sb, 5: sa >= sb,
                     6: a < b, 7: a >= b}[f3]
            if taken:
                npc = (self.pc + _sx(o, 13)) & M32
        elif op == 0x03:
            ad = (a + imm_i) & M32
            res = {0: lambda: self.load(ad, 1, True),
                   1: lambda: self.load(ad, 2, True),
                   2: lambda: self.load(ad, 4, False),
                   4: lambda: self.load(ad, 1, False),
                   5: lambda: self.load(ad, 2, False)}[f3]()
        elif op == 0x23:
            imm_s = _sx(((w >> 25) << 5) | ((w >> 7) & 0x1F), 12)
            ad = (a + imm_s) & M32
            self.store(ad, {0: 1, 1: 2, 2: 4}[f3], b)
        elif op == 0x13:
            sh = (w >> 20) & 0x1F
            res = {0: (a + imm_i), 2: int(sa < imm_i), 3: int(a < imm_i & M32),
                   4: a ^ imm_i, 6: a | imm_i, 7: a & imm_i,
                   1: a << sh,
                   5: (sa >> sh) if (f7 & 0x20) else (a >> sh)}[f3] & M32
        elif op == 0x33:
            res = {0: (a - b) if (f7 & 0x20) else (a + b),
                   1: a << (b & 31), 2: int(sa < sb), 3: int(a < b),
                   4: a ^ b,
                   5: (sa >> (b & 31)) if (f7 & 0x20) else (a >> (b & 31)),
                   6: a | b, 7: a & b}[f3] & M32
        elif op == 0x73:
            self.halted = True
            return
        elif op == 0x0F:
            pass
        else:
            raise ValueError(f"ISS: bad opcode {op:#x}")
        if res is not None and rd != 0:
            self.x[rd] = res & M32
        self.pc = npc

    def run(self, max_steps=10000):
        for _ in range(max_steps):
            if self.halted:
                return
            self.step()
        raise AssertionError("ISS did not halt")


# =====================================================================
# Gismo: resident microcode loader at 0xE00. Protocol over UART:
#   'L' a_hi a_lo n_hi n_lo then n 16-bit words (hi,lo): control store
#   'M' a_hi a_lo n_hi n_lo then n 32-bit words (MSB first): S-memory,
#       a is a 32-bit word address, autoincrementing
#   'G'                     jump to microaddress 0 (interpreter boot)
# A halted machine wakes into Gismo on the first received byte.
# =====================================================================

GISMO_BASE = 0xE00
GISMO_MAIN = 0xE10            # wake entry: skips the banner
# Console service ABI, MCP-style: resident Gismo exports fixed-address
# entry points that any loaded interpreter may CALL. Arguments: PUTC
# takes the byte in T; PUTHEX prints S10 as 8 hex digits; PUTS prints
# the zero-terminated string at F.A. Services clobber X, Y, T, S9.
SVC_PUTC   = 0xE05
SVC_PUTHEX = 0xE06
SVC_PUTS   = 0xE07
STR_BYTE   = 3840             # console text blob in S-memory (word 960)
STR_BITS   = STR_BYTE * 8

MENU_TEXT = ("\r\n== B2026 soft machine ==\r\n"
             "after the Burroughs B1700: the ISA lives in the store\r\n"
             "G: run loaded interpreter   ?: this menu\r\n"
             "L/M: binary loader blocks (b26_send.py)\r\nB26> ")

def strings_words():
    data = MENU_TEXT.encode('ascii') + b'\x00'
    data += b'\x00' * (-len(data) % 4)
    return [int.from_bytes(data[i:i+4], 'little')
            for i in range(0, len(data), 4)], STR_BYTE // 4

def _g_rx16_sub():
    # sub_rx16: S2 <- next two bytes as big-endian 16-bit (uses S1, S4)
    return ([('L', 'g_rx16'), ('CALL', 'g_rx'), MOVE(1, RX)]
            + 8 * m_double()
            + [MOVE(RX, 4), ('CALL', 'g_rx'), MOVE(1, RY),
               MOVE(4, RX), MOVE(SUM, 2), ('EXIT',)])

def _g_rx32_sub():
    # sub_rx32: S5 <- next four bytes as big-endian 32-bit
    body = [('L', 'g_rx32'), ('CALL', 'g_rx'), MOVE(1, RX)]
    for _ in range(3):
        body += [MOVE(RX, 4), ('CALL', 'g_rx'), MOVE(4, RX)]
        body += 8 * m_double()
        body += [MOVE(1, RY), MOVE(SUM, RX)]
    body += [MOVE(RX, 5), ('EXIT',)]
    return body

def _g_cmp_br(ch, lbl, nxt):
    # if S1 == ch: BR lbl (BR is full range, IF only skips)
    return [MOVE(1, RX), LIT(ord(ch)), MOVE(RT, RY), MOVE(XORR, RX),
            LIT(0), MOVE(RT, RY), ('IF', NZ, nxt), ('BR', lbl),
            ('L', nxt)]

def build_gismo():
    mc = [('ORG', GISMO_BASE)]
    # reset entry: print the console banner, then fall into main.
    # Wake-from-halt enters at GISMO_MAIN and skips the banner so that
    # binary loader streams never race the transmitter.
    mc += lit32(STR_BITS) + [MOVE(RT, FA_), ('CALL', 'g_puts'),
                             ('BR', 'g_main')]
    # service trampolines at frozen addresses (CALL here, BR keeps the
    # return address on the microstack)
    mc += [('ORG', SVC_PUTC),   ('BR', 'g_putc'),
           ('ORG', SVC_PUTHEX), ('BR', 'g_puthex'),
           ('ORG', SVC_PUTS),   ('BR', 'g_puts')]
    mc += [('ORG', GISMO_MAIN)]
    # main loop
    mc += [('L', 'g_main'), BIASL(32), ('CALL', 'g_rx')]
    mc += _g_cmp_br('L', 'g_L', 'g_c1')
    mc += _g_cmp_br('M', 'g_M', 'g_c2')
    mc += _g_cmp_br('G', 'g_G', 'g_c3')
    mc += _g_cmp_br('?', 'g_H', 'g_c4')
    mc += [('BR', 'g_main')]
    # '?': print the menu again
    mc += [('L', 'g_H')] + lit32(STR_BITS) + [MOVE(RT, FA_),
           ('CALL', 'g_puts'), ('BR', 'g_main')]
    # putc: send T[7:0], waiting out the transmitter
    mc += [('L', 'g_putc'),
           ('L', 'g_pcw'), ('IF', COND_TXB, 'g_pcw'),
           MOVE(RT, UTX), ('EXIT',)]
    # puthex: print S10 as 8 uppercase hex digits
    mc += [('L', 'g_puthex'),
           LIT(10), MOVE(RT, RY), LIT(0), MOVE(RT, RX),
           MOVE(DIFF, 9)]                       # S9 = -10
    for pos in range(28, -1, -4):
        la, lb = f'g_hxa{pos}', f'g_hxb{pos}'
        mc += [MOVE(10, RX), BIASL(4), EXTI(pos), BIASL(32),
               MOVE(RT, RX), MOVE(9, RY),
               ('IF', CYL, la),                 # nibble >= 10: letter
               LIT(48), ('BR', lb),             # '0' + n
               ('L', la), LIT(55),              # 'A' + n - 10
               ('L', lb), MOVE(RT, RY), MOVE(SUM, RT),
               ('CALL', 'g_putc')]
    mc += [('EXIT',)]
    # puts: zero-terminated string at F.A, defined-field byte reads
    mc += [('L', 'g_puts'), RD(C_T, cnt=3, ln=8),
           MOVE(RT, RX), LIT(0), MOVE(RT, RY), ('IF', Z, 'g_pdone'),
           ('L', 'g_pwait'), ('IF', COND_TXB, 'g_pwait'),
           MOVE(RX, UTX), ('BR', 'g_puts'),
           ('L', 'g_pdone'), ('EXIT',)]
    # byte receive: S1 <- byte
    mc += [('L', 'g_rx'), ('IF', 10, 'g_rxgo'), ('BR', 'g_rx'),
           ('L', 'g_rxgo'), MOVE(URX, 1), URXACK(), ('EXIT',)]
    mc += _g_rx16_sub()
    mc += _g_rx32_sub()
    # 'L': load control store words
    mc += [('L', 'g_L'), ('CALL', 'g_rx16'), MOVE(2, 6),
           ('CALL', 'g_rx16'), MOVE(2, 7),
           ('L', 'g_Lloop'), ('CALL', 'g_rx16'), MOVE(2, RT),
           MOVE(6, RX), CSW(),
           MOVE(6, RX), LIT(1), MOVE(RT, RY), MOVE(SUM, 6),
           MOVE(7, RX), MOVE(DIFF, 7),
           MOVE(7, RX), LIT(0), MOVE(RT, RY),
           ('IF', NZ, 'g_Lloop'), ('BR', 'g_main')]
    # 'M': load S-memory words (autoincrement via counting write)
    mc += [('L', 'g_M'), ('CALL', 'g_rx16'), MOVE(2, RX)]
    mc += 5 * m_double()
    mc += [MOVE(RX, SFA), ('CALL', 'g_rx16'), MOVE(2, 7), BIASL(32),
           ('L', 'g_Mloop'), ('CALL', 'g_rx32'),
           WR(5, sf=1, cnt=3),
           MOVE(7, RX), LIT(1), MOVE(RT, RY), MOVE(DIFF, 7),
           MOVE(7, RX), LIT(0), MOVE(RT, RY),
           ('IF', NZ, 'g_Mloop'), ('BR', 'g_main')]
    # 'G': jump to microaddress 0
    mc += [('L', 'g_G'), LIT(0), DISP(0)]
    return asm(mc)

# =====================================================================
# Second S-language: a byte-coded stack machine. Bytecode at byte 256,
# data stack at bit 24576 (byte 3072) growing upward. Push/pop are
# single counting FIU accesses through SF, exactly Wilner's
# write-and-push / read-and-pop.
# Opcodes: 00 HALT, 01 PUSHB imm8, 02 ADD, 03 SUB, 04 DUP, 05 DROP,
#          06 JNZ off8, 07 OUT
# =====================================================================

STK_STACK_BITS = 24576

def build_stack_interpreter():
    mc = [('ORG', 0)]
    mc += [LIT(CODE_BITS & 0xFFF)] + ([] if CODE_BITS < 4096 else [])
    mc += [MOVE(RT, FA_)]
    mc += lit32(STK_STACK_BITS) + [MOVE(RT, SFA), ('BR', 's_fetch')]
    mc += [('L', 's_fetch'), BIASL(8), RD(C_X, cnt=3),
           EXTI(0), DISP(1)]
    mc += [('ORG', 0x100 + 0x00), ('BR', 's_halt'),
           ('ORG', 0x100 + 0x01), ('BR', 's_pushb'),
           ('ORG', 0x100 + 0x02), ('BR', 's_add'),
           ('ORG', 0x100 + 0x03), ('BR', 's_sub'),
           ('ORG', 0x100 + 0x04), ('BR', 's_dup'),
           ('ORG', 0x100 + 0x05), ('BR', 's_drop'),
           ('ORG', 0x100 + 0x06), ('BR', 's_jnz'),
           ('ORG', 0x100 + 0x07), ('BR', 's_out')]
    mc += [('ORG', 0x180)]
    mc += [('L', 's_pushb'), RD(C_T, cnt=3), BIASL(32),
           MOVE(RT, 4), WR(4, sf=1, cnt=3), ('BR', 's_fetch')]
    mc += [('L', 's_add'), BIASL(32),
           RD(C_Y, sf=1, cnt=2), RD(C_X, sf=1, cnt=2),
           MOVE(SUM, 4), WR(4, sf=1, cnt=3), ('BR', 's_fetch')]
    mc += [('L', 's_sub'), BIASL(32),
           RD(C_Y, sf=1, cnt=2), RD(C_X, sf=1, cnt=2),
           MOVE(DIFF, 4), WR(4, sf=1, cnt=3), ('BR', 's_fetch')]
    mc += [('L', 's_dup'), BIASL(32), RD(C_X, sf=1, cnt=2),
           MOVE(RX, 4), WR(4, sf=1, cnt=3), WR(4, sf=1, cnt=3),
           ('BR', 's_fetch')]
    mc += [('L', 's_drop'), CNT(1, 1, 1, 32), ('BR', 's_fetch')]
    mc += [('L', 's_out'), BIASL(32), RD(C_T, sf=1, cnt=2),
           MONR(), MOVE(RT, 10), ('CALL', SVC_PUTHEX),
           LIT(13), ('CALL', SVC_PUTC),
           LIT(10), ('CALL', SVC_PUTC), ('BR', 's_fetch')]
    mc += [('L', 's_jnz'), RD(3, cnt=3), BIASL(32),
           RD(C_X, sf=1, cnt=2), LIT(0), MOVE(RT, RY),
           ('IF', Z, 's_jnz_no'),
           MOVE(3, RT)]
    mc += m_sext_T(8) + 3 * m_double()
    mc += [MOVE(FA_, RY), MOVE(SUM, FA_),
           ('L', 's_jnz_no'), ('BR', 's_fetch')]
    mc += [('L', 's_halt'), HALT()]
    prog = asm(mc)
    assert max(prog) < GISMO_BASE
    return prog

def stk_asm(items):
    out = []
    for it in items:
        if isinstance(it, tuple):
            op, arg = it
            out += [{'pushb': 1, 'jnz': 6}[op], arg & 0xFF]
        else:
            out.append({'halt': 0, 'add': 2, 'sub': 3, 'dup': 4,
                        'drop': 5, 'out': 7}[it])
    words = []
    for i in range(0, len(out), 4):
        w = 0
        for j, b in enumerate(out[i:i+4]):
            w |= b << (8 * j)
        words.append(w)
    return words

# =====================================================================
# Loader stream builder: image dict -> UART byte stream
# =====================================================================

def _runs(prog):
    addrs = sorted(prog)
    runs, start, prev = [], addrs[0], addrs[0]
    for a in addrs[1:]:
        if a != prev + 1:
            runs.append((start, prev))
            start = a
        prev = a
    runs.append((start, prev))
    return runs

def loader_stream(cs_image=None, mem_words=None, mem_word_addr=None,
                  go=False):
    out = bytearray()
    if cs_image:
        for s, e in _runs(cs_image):
            n = e - s + 1
            out += b'L' + s.to_bytes(2, 'big') + n.to_bytes(2, 'big')
            for a in range(s, e + 1):
                out += cs_image[a].to_bytes(2, 'big')
    if mem_words:
        out += b'M' + mem_word_addr.to_bytes(2, 'big')              + len(mem_words).to_bytes(2, 'big')
        for w in mem_words:
            out += w.to_bytes(4, 'big')
    if go:
        out += b'G'
    return bytes(out)
