// b2026 compare tb_serv v0.1 (20260822)
// Cycle counter for the CPI comparison: runs the reference program and
// stops when the core stores to the LED port.
`timescale 1ns/1ps
module tb_serv;
    reg clk = 0, btn1_n = 1;
    wire [5:0] led;
    always #5 clk = ~clk;
    serv_fpga dut(.sys_clk(clk), .btn1_n(btn1_n), .led(led));
    integer n = 0;
    reg started = 0;
    // count from the cycle the natural power-on reset releases
    always @(posedge clk) if (dut.por[15]) started <= 1;
    always @(posedge clk) if (started) begin
        n = n + 1;
        if (dut.ledr != 0) begin
            $display("SERV cycles=%0d led=%0d", n, dut.ledr);
            $finish;
        end
        if (n > 3000000) begin
            $display("SERV TIMEOUT");
            $finish;
        end
    end
endmodule
