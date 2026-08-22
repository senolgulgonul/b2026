// b2026 b26_fpga v0.3 (20260821)
// Tang Nano 9K top: b26 core + inferred BSRAM control store and S-memory,
// power-on reset, button reset, monitor port on the LEDs.
//
// Runs directly from the 27 MHz crystal, no PLL. Memories are written as
// plain inferrable synchronous RAM so Gowin synthesis maps them to BSRAM;
// $readmemh loads the interpreter and the demo program at bitstream time.
// LEDs are active low: led = ~mon[5:0]. The demo leaves 55 (0b110111) on
// the monitor, so the visible pattern is one dark LED at bit 3.

module cs_ram #(
    parameter INIT = "cs_init.hex"
) (
    input  wire        clk,
    input  wire        re,
    input  wire [11:0] addr,
    output reg  [15:0] rdata,
    input  wire        we,
    input  wire [11:0] waddr,
    input  wire [15:0] wdata
);
    reg [15:0] mem [0:4095];
    initial $readmemh(INIT, mem);
    always @(posedge clk) begin
        if (we) mem[waddr] <= wdata;
        if (re) rdata <= mem[addr];
    end
endmodule

module smem_ram #(
    parameter INIT = "smem_init.hex"
) (
    input  wire        clk,
    input  wire        re,
    input  wire        we,
    input  wire [11:0] addr,
    input  wire [31:0] wdata,
    output reg  [31:0] rdata
);
    reg [31:0] mem [0:4095];
    initial $readmemh(INIT, mem);
    always @(posedge clk) begin
        if (we) mem[addr] <= wdata;
        if (re) rdata <= mem[addr];
    end
endmodule

module b26_fpga (
    input  wire       sys_clk,   // 27 MHz crystal
    input  wire       btn1_n,    // user button S1, active low: reset
    input  wire       uart_rx,   // from the on-board USB serial bridge
    output wire       uart_tx,   // to the bridge: console banner and menu
    output wire [5:0] led        // active low
);
    wire clk = sys_clk;

    // power-on reset plus synchronized button reset
    reg [15:0] por = 16'd0;
    always @(posedge clk)
        if (!por[15]) por <= por + 16'd1;
    reg bs0 = 1'b1, bs1 = 1'b1;
    always @(posedge clk) begin
        bs0 <= btn1_n;
        bs1 <= bs0;
    end
    wire rst = ~por[15] | ~bs1;

    wire [11:0] cs_addr;
    wire        cs_re;
    wire [15:0] cs_rdata;
    wire        cs_we;
    wire [11:0] cs_waddr;
    wire [15:0] cs_wdata;
    wire [18:0] m_addr;
    wire        m_re, m_we;
    wire [31:0] m_wdata, m_rdata;
    wire        halted;
    wire [7:0]  mon;

    b26 #(.RESET_ADDR(12'hE00)) u_core (   // power-on boots the console
        .clk(clk), .rst(rst),
        .cs_addr(cs_addr), .cs_re(cs_re), .cs_rdata(cs_rdata),
        .cs_we(cs_we), .cs_waddr(cs_waddr), .cs_wdata(cs_wdata),
        .uart_rxp(uart_rx), .uart_txp(uart_tx),
        .m_addr(m_addr), .m_re(m_re), .m_we(m_we),
        .m_wdata(m_wdata), .m_rdata(m_rdata),
        .halted(halted), .mon(mon)
    );

    cs_ram u_cs (
        .clk(clk), .re(cs_re), .addr(cs_addr), .rdata(cs_rdata),
        .we(cs_we), .waddr(cs_waddr), .wdata(cs_wdata)
    );

    smem_ram u_sm (
        .clk(clk), .re(m_re), .we(m_we), .addr(m_addr[11:0]),
        .wdata(m_wdata), .rdata(m_rdata)
    );

    assign led = ~mon[5:0];

endmodule
