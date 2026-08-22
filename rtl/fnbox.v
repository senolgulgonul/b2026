// b2026 fnbox v0.1 (20260821)
// B1700-style function box: X and Y feed a combinational box biased by CPL.
// Outputs are read-only pseudo-registers; flags follow SUM under CPL bias.
// Vendor-neutral Verilog-2001, no FPGA primitives.

module fnbox (
    input  wire [31:0] x,
    input  wire [31:0] y,
    input  wire [5:0]  cpl,    // effective operand length, valid 1..32
    output wire [31:0] sum,
    output wire [31:0] diff,
    output wire [31:0] andr,
    output wire [31:0] orr,
    output wire [31:0] xorr,
    output wire [31:0] mskx,
    output wire        cyl,    // carry out of bit CPL-1 of SUM
    output wire        z,      // SUM masked to CPL is zero
    output wire        n       // bit CPL-1 of SUM
);

    wire [31:0] mask = (cpl >= 6'd32) ? 32'hFFFF_FFFF
                                      : ((32'h1 << cpl) - 32'h1);

    wire [31:0] xm = x & mask;
    wire [31:0] ym = y & mask;

    wire [32:0] s  = {1'b0, xm} + {1'b0, ym};
    wire [32:0] d  = {1'b0, xm} - {1'b0, ym};

    assign sum  = s[31:0] & mask;
    assign diff = d[31:0] & mask;
    assign andr = xm & ym;
    assign orr  = xm | ym;
    assign xorr = xm ^ ym;
    assign mskx = xm;

    assign cyl = s[cpl];            // carry lands one past the top bit
    assign z   = (sum == 32'h0);
    assign n   = sum[cpl - 6'd1];

endmodule
