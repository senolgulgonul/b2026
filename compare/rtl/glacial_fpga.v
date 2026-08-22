// b2026 compare glacial_fpga v0.1 (20260822)
// Glacial (brouhaha/glacial, BSD-2-Clause) on the Tang Nano 9K, wrapped
// to match the comparison harness. Glacial keeps microcode, scratchpad
// and RISC-V memory in one byte-wide RAM, so the wrapper differs from
// the SERV and PicoRV32 ones: 16 KB of byte-wide BSRAM instead of
// 4096 x 32, and the result byte is latched from a store to the top of
// memory rather than a word-wide MMIO port.
//
// 64 KB would exceed the GW1NR-9's 468 Kbit of BSRAM, so the address
// space is truncated to 16 KB, which still holds the microcode, the
// scratchpad and a small program.

module glacial_fpga (
    input  wire       sys_clk,
    input  wire       btn1_n,
    output wire [5:0] led,
    output wire       uart_tx
);
    wire clk = sys_clk;

    reg [15:0] por = 16'd0;
    always @(posedge clk)
        if (!por[15]) por <= por + 16'd1;
    reg bs0 = 1'b1, bs1 = 1'b1;
    always @(posedge clk) begin
        bs0 <= btn1_n;
        bs1 <= bs0;
    end
    wire reset = ~por[15] | ~bs1;

    wire [15:0] mem_addr;
    wire        mem_rd_en, mem_wr_en;
    wire  [7:0] mem_wr_data;
    reg   [7:0] mem_rd_data;

    reg [7:0] mem [0:16383];
    initial $readmemh("glacial_init.hex", mem);

    localparam [13:0] RESULT_ADDR = 14'h29FC;   // 0x0A00 + 0x1FFC
    reg [5:0] ledr = 6'd0;
    wire      led_sel = mem_wr_en & (mem_addr[13:0] == RESULT_ADDR);

    always @(posedge clk) begin
        if (mem_wr_en)
            mem[mem_addr[13:0]] <= mem_wr_data;
        else if (mem_rd_en)
            mem_rd_data <= mem[mem_addr[13:0]];
        if (led_sel)
            ledr <= mem_wr_data[5:0];
    end

    glacial u_cpu (
        .clk(clk), .reset(reset),
        .mem_addr(mem_addr), .mem_rd_en(mem_rd_en),
        .mem_rd_data(mem_rd_data), .mem_wr_en(mem_wr_en),
        .mem_wr_data(mem_wr_data),
        .xint(1'b0), .xtick(1'b0), .uart_tx(uart_tx)
    );

    assign led = ~ledr;
endmodule
