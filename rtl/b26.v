// b2026 b26 v0.4 (20260821)
// Top-level micromachine: useq + fnbox + fiu + register namespace and
// execute logic. Control store and S-memory are external ports so the
// same core simulates behaviorally and later wraps Gowin BSRAM.
//
// Register namespace (6-bit), read mux "rd6":
//   0x00..0x0F  S0..S15 scratchpad
//   0x10 X   0x11 Y   0x12 T
//   0x13 F.A  0x14 F.L  0x15 SF.A  0x16 SF.L  0x17 CPL
//   0x18 SUM 0x19 DIFF 0x1A ANDR 0x1B ORR 0x1C XORR 0x1D MSKX (read only)
//   0x1E ZERO 0x1F ONES (read only)
// Compact 4-bit map for READ dest / WRITE src: 0..11 S0..S11,
// 12 X, 13 Y, 14 T, 15 reserved.
//
// READ/WRITE count modes [6:5]: 0 none, 1 A up L down, 2 A down L down
// (backward access, fd=1), 3 A up only. Access length [4:0]: 0 means CPL,
// else literal 1..31. Counting and dest writeback commit when the FIU
// finishes; the sequencer is stalled meanwhile.

module b26 (
    input  wire        clk,
    input  wire        rst,
    // control store, synchronous read with clock enable
    output wire [11:0] cs_addr,
    output wire        cs_re,
    input  wire [15:0] cs_rdata,
    output wire        cs_we,
    output wire [11:0] cs_waddr,
    output wire [15:0] cs_wdata,
    // S-memory, synchronous read
    output wire [18:0] m_addr,
    output wire        m_re,
    output wire        m_we,
    output wire [31:0] m_wdata,
    input  wire [31:0] m_rdata,
    output wire        halted,
    output reg  [7:0]  mon,
    input  wire        uart_rxp,
    output wire        uart_txp
);
    parameter BAUD_DIV   = 234;
    parameter RESET_ADDR = 12'h000;
    parameter WAKE_ADDR  = 12'hE10;

    // ---------------- registers ----------------
    reg [31:0] sregs [0:15];
    reg [31:0] rx, ry, rt;
    reg [23:0] f_a, sf_a;
    reg [15:0] f_l, sf_l;
    reg [5:0]  cpl;

    // ---------------- uart ----------------
    wire [7:0] u_data;
    wire       u_valid;
    wire       u_ack;

    uart_rx #(.BAUD_DIV(BAUD_DIV)) u_uart (
        .clk(clk), .rst(rst), .rxd(uart_rxp),
        .data(u_data), .valid(u_valid), .ack(u_ack)
    );

    wire       utx_we;
    wire [7:0] utx_data;
    wire       utx_busy;

    uart_tx #(.BAUD_DIV(BAUD_DIV)) u_utx (
        .clk(clk), .rst(rst), .we(utx_we), .data(utx_data),
        .txd(uart_txp), .busy(utx_busy)
    );

    // ---------------- function box ----------------
    wire [31:0] w_sum, w_diff, w_andr, w_orr, w_xorr, w_mskx;
    wire        w_cyl, w_z, w_n;

    fnbox u_fnb (
        .x(rx), .y(ry), .cpl(cpl),
        .sum(w_sum), .diff(w_diff), .andr(w_andr),
        .orr(w_orr), .xorr(w_xorr), .mskx(w_mskx),
        .cyl(w_cyl), .z(w_z), .n(w_n)
    );

    // ---------------- sequencer ----------------
    wire [15:0] ui;
    wire [11:0] upc;
    wire        uvld;
    wire        stall;

    useq #(.RESET_ADDR(RESET_ADDR), .WAKE_ADDR(WAKE_ADDR)) u_seq (
        .clk(clk), .rst(rst),
        .cs_addr(cs_addr), .cs_re(cs_re), .cs_rdata(cs_rdata),
        .uinstr(ui), .upc(upc), .uvalid(uvld),
        .stall(stall),
        .f_z(w_z), .f_cyl(w_cyl), .f_n(w_n),
        .f_fl0(f_l == 16'd0), .f_sfl0(sf_l == 16'd0), .f_int(u_valid),
        .f_txb(utx_busy),
        .disp_t(rt[7:0]),
        .halted(halted)
    );

    // ---------------- decode ----------------
    wire [3:0] cls = ui[15:12];
    wire is_move = (cls == 4'h0);
    wire is_lit  = (cls == 4'h1);
    wire is_lits = (cls == 4'h2);
    wire is_rd   = (cls == 4'h3);
    wire is_wr   = (cls == 4'h4);
    wire is_ext  = (cls == 4'h5);
    wire is_bias = (cls == 4'hB);
    wire is_cnt  = (cls == 4'hC);
    wire is_ctrl = (cls == 4'hF);
    wire is_mem  = is_rd | is_wr;

    // ---------------- FIU ----------------
    wire        fiu_busy, fiu_done;
    wire [31:0] fiu_rf;

    wire        fsel  = ui[7];
    wire [1:0]  cmode = ui[6:5];
    wire [5:0]  alen  = (ui[4:0] == 5'd0) ? cpl : {1'b0, ui[4:0]};
    wire [23:0] fiu_fa = fsel ? sf_a : f_a;
    wire        fiu_fd = (cmode == 2'd2);

    assign stall = uvld && is_mem && !fiu_done;
    wire adv     = uvld && !stall;
    wire fiu_req = uvld && is_mem && !fiu_busy && !fiu_done;

    // 4-bit compact register read (WRITE source)
    reg [31:0] r4v;
    always @* begin
        if (ui[11:8] <= 4'd11)      r4v = sregs[ui[11:8]];
        else if (ui[11:8] == 4'd12) r4v = rx;
        else if (ui[11:8] == 4'd13) r4v = ry;
        else if (ui[11:8] == 4'd14) r4v = rt;
        else                        r4v = 32'd0;
    end

    fiu u_fiu (
        .clk(clk), .rst(rst),
        .req(fiu_req), .wr(is_wr),
        .fa(fiu_fa), .len(alen), .fd(fiu_fd), .wdata(r4v),
        .busy(fiu_busy), .done(fiu_done), .rfield(fiu_rf),
        .m_addr(m_addr), .m_re(m_re), .m_we(m_we),
        .m_wdata(m_wdata), .m_rdata(m_rdata)
    );

    // ---------------- 6-bit register read mux ----------------
    wire [5:0] src6 = ui[11:6];
    reg [31:0] rd6;
    always @* begin
        if (src6[5:4] == 2'b00) rd6 = sregs[src6[3:0]];
        else case (src6)
            6'h10: rd6 = rx;
            6'h11: rd6 = ry;
            6'h12: rd6 = rt;
            6'h13: rd6 = {8'd0, f_a};
            6'h14: rd6 = {16'd0, f_l};
            6'h15: rd6 = {8'd0, sf_a};
            6'h16: rd6 = {16'd0, sf_l};
            6'h17: rd6 = {26'd0, cpl};
            6'h18: rd6 = w_sum;
            6'h19: rd6 = w_diff;
            6'h1A: rd6 = w_andr;
            6'h1B: rd6 = w_orr;
            6'h1C: rd6 = w_xorr;
            6'h1D: rd6 = w_mskx;
            6'h1E: rd6 = 32'd0;
            6'h1F: rd6 = 32'hFFFF_FFFF;
            6'h20: rd6 = {24'd0, u_data};
            default: rd6 = 32'd0;
        endcase
    end

    wire [31:0] cplmask = (cpl >= 6'd32) ? 32'hFFFF_FFFF
                                         : ((32'h1 << cpl) - 32'h1);

    // normalize a CPL write: 0 or over 32 becomes 32
    function [5:0] cplnorm(input [5:0] v);
        cplnorm = (v == 6'd0 || v > 6'd32) ? 6'd32 : v;
    endfunction

    // counting amounts
    wire [23:0] cnt_ka = ui[8] ? {16'd0, ui[7:0]} : {18'd0, cpl};
    wire [15:0] cnt_kl = ui[8] ? {8'd0, ui[7:0]}  : {10'd0, cpl};
    wire [23:0] mem_ka = {18'd0, alen};
    wire [15:0] mem_kl = {10'd0, alen};

    // CTRL side effects outside the register commit block
    wire is_sub4 = is_ctrl && (ui[11:8] == 4'h4);
    wire is_sub5 = is_ctrl && (ui[11:8] == 4'h5);
    assign u_ack    = adv && is_sub4;              // URXACK
    assign utx_we   = adv && is_move && (dst6 == 6'h21);   // MOVE x -> UTX
    assign utx_data = rd6[7:0];
    assign cs_we    = adv && is_sub5;              // CSW: cs[X] <- T
    assign cs_waddr = rx[11:0];
    assign cs_wdata = rt[15:0];

    // ---------------- execute / commit ----------------
    wire [5:0] dst6 = ui[5:0];
    wire [3:0] d4   = ui[11:8];

    always @(posedge clk) begin
        if (rst) begin
            rx <= 32'd0; ry <= 32'd0; rt <= 32'd0;
            f_a <= 24'd0; f_l <= 16'd0; sf_a <= 24'd0; sf_l <= 16'd0;
            cpl <= 6'd32;
            mon <= 8'd0;
        end else if (adv) begin
            case (cls)
                4'h0: begin // MOVE
                    if (dst6[5:4] == 2'b00) sregs[dst6[3:0]] <= rd6;
                    else case (dst6)
                        6'h10: rx   <= rd6;
                        6'h11: ry   <= rd6;
                        6'h12: rt   <= rd6;
                        6'h13: f_a  <= rd6[23:0];
                        6'h14: f_l  <= rd6[15:0];
                        6'h15: sf_a <= rd6[23:0];
                        6'h16: sf_l <= rd6[15:0];
                        6'h17: cpl  <= cplnorm(rd6[5:0]);
                        default: ;  // read-only names: ignored
                    endcase
                end
                4'h1: rt <= {20'd0, ui[11:0]};              // LIT
                4'h2: rt <= {rt[19:0], ui[11:0]};           // LITS
                4'h3, 4'h4: begin                           // READ / WRITE
                    if (is_rd) begin
                        if (d4 <= 4'd11)      sregs[d4] <= fiu_rf;
                        else if (d4 == 4'd12) rx <= fiu_rf;
                        else if (d4 == 4'd13) ry <= fiu_rf;
                        else if (d4 == 4'd14) rt <= fiu_rf;
                    end
                    if (!fsel) begin
                        case (cmode)
                            2'd1: begin f_a <= f_a + mem_ka;
                                        f_l <= f_l - mem_kl; end
                            2'd2: begin f_a <= f_a - mem_ka;
                                        f_l <= f_l - mem_kl; end
                            2'd3: f_a <= f_a + mem_ka;
                            default: ;
                        endcase
                    end else begin
                        case (cmode)
                            2'd1: begin sf_a <= sf_a + mem_ka;
                                        sf_l <= sf_l - mem_kl; end
                            2'd2: begin sf_a <= sf_a - mem_ka;
                                        sf_l <= sf_l - mem_kl; end
                            2'd3: sf_a <= sf_a + mem_ka;
                            default: ;
                        endcase
                    end
                end
                4'h5: rt <= (rx >> ui[11:6]) & cplmask;     // EXT
                4'hB: case (ui[11:8])                       // BIAS
                    4'd0: cpl <= cplnorm(ui[5:0]);
                    4'd1: cpl <= (f_l  > 16'd32) ? 6'd32 : f_l[5:0];
                    4'd2: cpl <= (sf_l > 16'd32) ? 6'd32 : sf_l[5:0];
                    default: ;
                endcase
                4'hC: begin                                 // CNT
                    if (!ui[11]) case (ui[10:9])
                        2'd0: f_a <= f_a + cnt_ka;
                        2'd1: f_a <= f_a - cnt_ka;
                        2'd2: f_l <= f_l - cnt_kl;
                        2'd3: begin f_a <= f_a + cnt_ka;
                                    f_l <= f_l - cnt_kl; end
                    endcase
                    else case (ui[10:9])
                        2'd0: sf_a <= sf_a + cnt_ka;
                        2'd1: sf_a <= sf_a - cnt_ka;
                        2'd2: sf_l <= sf_l - cnt_kl;
                        2'd3: begin sf_a <= sf_a + cnt_ka;
                                    sf_l <= sf_l - cnt_kl; end
                    endcase
                end
                4'hF: case (ui[11:8])
                    4'h2: mon <= ui[7:0];       // MONITOR imm8
                    4'h3: mon <= rt[7:0];       // MONR: mon <- T
                    default: ;
                endcase
                default: ;
            endcase
        end
    end

endmodule
