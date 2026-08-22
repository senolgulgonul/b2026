// b2026 compare picorv32_fpga v0.2 (20260822)
// PicoRV32 on the Tang Nano 9K with the same harness as serv_fpga:
// one 4096 x 32 BSRAM, 27 MHz, LEDs latched from a store to byte 4092.
//
// Configured for a size-comparable build: no counters, no two-stage
// shift, compressed and mul disabled, which is the usual "small"
// PicoRV32 profile.

module picorv32_fpga (
    input  wire       sys_clk,
    input  wire       btn1_n,
    output wire [5:0] led
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
    wire resetn = por[15] & bs1;

    wire        mem_valid, mem_instr;
    reg         mem_ready;
    wire [31:0] mem_addr, mem_wdata;
    wire [3:0]  mem_wstrb;
    wire [31:0] mem_rdata;

    reg [31:0] mem [0:4095];
    initial $readmemh("picorv32_init.hex", mem);

    reg [5:0] ledr = 6'd0;
    wire      led_sel = mem_valid & (|mem_wstrb) & (mem_addr[13:2] == 12'h3FF);

    // plain 32-bit BSRAM: byte lanes merged in logic (see serv_fpga)
    wire        do_wr = mem_valid & (|mem_wstrb) & ~mem_ready & ~led_sel;
    reg  [31:0] rdt_r;
    wire [31:0] wmerge = {
        mem_wstrb[3] ? mem_wdata[31:24] : rdt_r[31:24],
        mem_wstrb[2] ? mem_wdata[23:16] : rdt_r[23:16],
        mem_wstrb[1] ? mem_wdata[15:8]  : rdt_r[15:8],
        mem_wstrb[0] ? mem_wdata[7:0]   : rdt_r[7:0]};

    always @(posedge clk) begin
        if (do_wr)
            mem[mem_addr[13:2]] <= wmerge;
        else
            rdt_r <= mem[mem_addr[13:2]];
    end
    assign mem_rdata = rdt_r;

    always @(posedge clk) begin
        mem_ready <= mem_valid & ~mem_ready;
        if (mem_valid & (|mem_wstrb) & ~mem_ready & led_sel)
            ledr <= mem_wdata[5:0];
    end

    picorv32 #(
        .ENABLE_COUNTERS(0),
        .ENABLE_COUNTERS64(0),
        .TWO_STAGE_SHIFT(0),
        .CATCH_MISALIGN(0),
        .CATCH_ILLINSN(0),
        .COMPRESSED_ISA(0),
        .ENABLE_MUL(0),
        .ENABLE_DIV(0),
        .ENABLE_IRQ(0),
        .PROGADDR_RESET(32'h0000_0100)
    ) u_cpu (
        .clk(clk), .resetn(resetn),
        .mem_valid(mem_valid), .mem_instr(mem_instr),
        .mem_ready(mem_ready), .mem_addr(mem_addr),
        .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb),
        .mem_rdata(mem_rdata),
        .mem_la_read(), .mem_la_write(), .mem_la_addr(),
        .mem_la_wdata(), .mem_la_wstrb(),
        .pcpi_valid(), .pcpi_insn(), .pcpi_rs1(), .pcpi_rs2(),
        .pcpi_wr(1'b0), .pcpi_rd(32'd0), .pcpi_wait(1'b0),
        .pcpi_ready(1'b0),
        .irq(32'd0), .eoi(),
        .trace_valid(), .trace_data()
    );

    assign led = ~ledr;
endmodule
