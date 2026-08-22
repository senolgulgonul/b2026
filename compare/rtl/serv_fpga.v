// b2026 compare serv_fpga v0.2 (20260822)
// SERV on the Tang Nano 9K, wrapped to match the b2026 comparison
// harness: one 4096 x 32 BSRAM holding code and data, 27 MHz, no PLL,
// six active-low LEDs driven by a store to MMIO word 0xFFF (byte 4092).
//
// The wrapper is deliberately thin: no CSRs, no timer, no peripherals
// beyond the LED latch, so the resource numbers reflect the core.

module serv_fpga (
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
    wire rst = ~por[15] | ~bs1;

    wire [31:0] ibus_adr, dbus_adr, dbus_dat, dbus_rdt;
    wire [3:0]  dbus_sel;
    wire        ibus_cyc, dbus_we, dbus_cyc;
    reg  [31:0] ibus_rdt;
    reg         ibus_ack, dbus_ack;

    reg [31:0] mem [0:4095];
    initial $readmemh("serv_init.hex", mem);

    reg [5:0] ledr = 6'd0;
    wire      led_sel = dbus_cyc & dbus_we & (dbus_adr[13:2] == 12'h3FF);

    // Single-port BSRAM shared by both buses. Byte lanes are merged in
    // logic (read data is already registered from the previous cycle),
    // so the RAM sees plain 32-bit writes: no byte enables, no
    // write-through mode, which is what GW1NR-9 BSRAM supports.
    wire        d_wr  = dbus_cyc & dbus_we & ~dbus_ack;
    wire [11:0] a_sel = d_wr ? dbus_adr[13:2] : ibus_adr[13:2];
    reg  [31:0] rdt_r;
    reg  [31:0] dbus_rdt_r;

    wire [31:0] wmerge = {
        dbus_sel[3] ? dbus_dat[31:24] : dbus_rdt_r[31:24],
        dbus_sel[2] ? dbus_dat[23:16] : dbus_rdt_r[23:16],
        dbus_sel[1] ? dbus_dat[15:8]  : dbus_rdt_r[15:8],
        dbus_sel[0] ? dbus_dat[7:0]   : dbus_rdt_r[7:0]};

    always @(posedge clk) begin
        if (d_wr & ~led_sel)
            mem[a_sel] <= wmerge;
        else
            rdt_r <= mem[a_sel];
    end

    always @(posedge clk) begin
        ibus_ack   <= ibus_cyc & ~ibus_ack & ~d_wr;
        dbus_ack   <= dbus_cyc & ~dbus_ack;
        dbus_rdt_r <= rdt_r;
        if (dbus_cyc & dbus_we & ~dbus_ack & led_sel)
            ledr <= dbus_dat[5:0];
    end

    always @* ibus_rdt = rdt_r;
    assign dbus_rdt = rdt_r;

    serv_rf_top #(.WITH_CSR(0), .RESET_PC(32'h0000_0100)) u_cpu (
        .clk(clk), .i_rst(rst), .i_timer_irq(1'b0),
        .o_ibus_adr(ibus_adr), .o_ibus_cyc(ibus_cyc),
        .i_ibus_rdt(ibus_rdt), .i_ibus_ack(ibus_ack),
        .o_dbus_adr(dbus_adr), .o_dbus_dat(dbus_dat),
        .o_dbus_sel(dbus_sel), .o_dbus_we(dbus_we),
        .o_dbus_cyc(dbus_cyc), .i_dbus_rdt(dbus_rdt),
        .i_ext_rd(32'd0), .i_ext_ready(1'b0),
        .i_dbus_ack(dbus_ack)
    );

    assign led = ~ledr;
endmodule
