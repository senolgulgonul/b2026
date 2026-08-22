// b2026 useq v0.3 (20260821)
// Microsequencer: overlapped fetch/execute against a synchronous
// control store (BSRAM-like, 1-cycle read latency).
//
// The next fetch address is a combinational function of the currently
// executing microinstruction, so taken control transfers cost no bubble:
// every micro is single cycle unless the datapath asserts stall.
//
// Flow-control classes handled here (spec v0.1 section 4):
//   6 BR    MPC <- MPC + simm12
//   7 IF    if cond then MPC <- MPC + simm8
//   8 CALL  push MPC+1, MPC <- abs12
//   9 EXIT  MPC <- pop
//   A DISP  MPC <- {page[3:0], T[7:0]}
//   F CTRL  sub 0 NOP, sub 1 HALT (other subops belong to the datapath)
// All other classes are datapath operations and fall through as MPC+1.
//
// Conditions [11:8] of IF: 0 Z, 1 NZ, 2 CYL, 3 NCYL, 4 N, 5 NN,
// 6 FL0, 7 FLNZ, 8 SFL0, 9 SFLNZ, 10 INT, 11 TRUE, 12..15 false.

module useq (
    input  wire        clk,
    input  wire        rst,
    // control store, synchronous read
    output wire [11:0] cs_addr,
    output wire        cs_re,
    input  wire [15:0] cs_rdata,
    // executing microinstruction, to the datapath
    output wire [15:0] uinstr,
    output wire [11:0] upc,
    output wire        uvalid,
    input  wire        stall,     // datapath busy: freeze everything
    // condition flags from the datapath
    input  wire        f_z,
    input  wire        f_cyl,
    input  wire        f_n,
    input  wire        f_fl0,
    input  wire        f_sfl0,
    input  wire        f_int,
    input  wire        f_txb,
    // dispatch index from the datapath (T[7:0])
    input  wire [7:0]  disp_t,
    output reg         halted
);
    parameter [11:0] RESET_ADDR = 12'h000;
    parameter [11:0] WAKE_ADDR  = 12'hE10;  // Gismo main, skips the banner

    reg  [11:0] fpc;            // sequential next fetch address
    reg  [11:0] xpc;            // address of the executing micro
    reg         xvld;

    reg  [11:0] stk [0:15];     // microstack
    reg  [3:0]  sp;

    wire [3:0] cls  = cs_rdata[15:12];
    wire is_br   = (cls == 4'h6);
    wire is_if   = (cls == 4'h7);
    wire is_call = (cls == 4'h8);
    wire is_exit = (cls == 4'h9);
    wire is_disp = (cls == 4'hA);
    wire is_halt = (cls == 4'hF) && (cs_rdata[11:8] == 4'h1);

    reg cval;
    always @* begin
        case (cs_rdata[11:8])
            4'd0:  cval = f_z;
            4'd1:  cval = ~f_z;
            4'd2:  cval = f_cyl;
            4'd3:  cval = ~f_cyl;
            4'd4:  cval = f_n;
            4'd5:  cval = ~f_n;
            4'd6:  cval = f_fl0;
            4'd7:  cval = ~f_fl0;
            4'd8:  cval = f_sfl0;
            4'd9:  cval = ~f_sfl0;
            4'd10: cval = f_int;
            4'd11: cval = 1'b1;
            4'd12: cval = f_txb;
            default: cval = 1'b0;
        endcase
    end

    wire ex    = xvld && !halted;
    wire taken = ex && (is_br || is_call || is_disp || is_exit
                        || (is_if && cval));

    reg [11:0] target;
    always @* begin
        if (is_exit)      target = stk[sp - 4'd1];
        else if (is_call) target = cs_rdata[11:0];
        else if (is_disp) target = {cs_rdata[11:8], disp_t};
        else if (is_if)   target = xpc + {{4{cs_rdata[7]}}, cs_rdata[7:0]};
        else              target = xpc + cs_rdata[11:0];   // BR, mod 4096
    end

    wire [11:0] nfetch = taken ? target : fpc;

    assign cs_addr = nfetch;
    assign cs_re   = !stall && !halted;
    assign uinstr  = cs_rdata;
    assign upc     = xpc;
    assign uvalid  = ex;

    always @(posedge clk) begin
        if (rst) begin
            fpc    <= RESET_ADDR;
            xpc    <= 12'd0;
            xvld   <= 1'b0;
            sp     <= 4'd0;
            halted <= 1'b0;
        end else if (halted && f_int) begin
            // Gismo wake: any UART byte revives a halted machine into the
            // resident loader, B1700 console style
            halted <= 1'b0;
            xvld   <= 1'b0;
            fpc    <= WAKE_ADDR;
        end else if (!stall && !halted) begin
            if (ex && is_halt) begin
                halted <= 1'b1;
                xvld   <= 1'b0;
            end else begin
                xpc  <= nfetch;
                fpc  <= nfetch + 12'd1;
                xvld <= 1'b1;
                if (ex && is_call) begin
                    stk[sp] <= xpc + 12'd1;
                    sp      <= sp + 4'd1;
                end
                if (ex && is_exit)
                    sp <= sp - 4'd1;
            end
        end
    end

endmodule
