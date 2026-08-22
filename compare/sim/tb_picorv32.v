// b2026 compare tb_picorv32 v0.1 (20260822)
`timescale 1ns/1ps
module tb_picorv32;
    reg clk = 0, btn1_n = 1;
    wire [5:0] led;
    always #5 clk = ~clk;
    picorv32_fpga dut(.sys_clk(clk), .btn1_n(btn1_n), .led(led));
    integer n = 0;
    reg started = 0;
    always @(posedge clk) if (dut.por[15]) started <= 1;
    always @(posedge clk) if (started) begin
        n = n + 1;
        if (dut.ledr != 0) begin
            $display("PICORV32 cycles=%0d led=%0d", n, dut.ledr);
            $finish;
        end
        if (n > 3000000) begin
            $display("PICORV32 TIMEOUT");
            $finish;
        end
    end
endmodule
