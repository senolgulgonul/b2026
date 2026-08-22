// b2026 compare tb_glacial v0.2 (20260822)
// Glacial CPI measurement using the core's own instruction-retire
// microcode address (phase 3 at upc 0x0f4), following the upstream
// testbench's clocking and trace point.
module tb_glacial;
   wire [15:0] mem_addr;
   wire        mem_rd_en, mem_wr_en;
   wire  [7:0] mem_rd_data, mem_wr_data;
   wire        uart_tx;
   reg         reset = 1;
   reg [31:0]  cycle = 0;
   reg         clk = 0;
   integer     ninstr = 0;
   reg         seen = 0;

   always #10 begin
     if (clk) begin
       clk = 0;
       reset = 0;
     end else begin
       clk = 1;
       cycle += 1;
     end
   end

   // her RISC-V komut yurutmesinde mikro pc 0x0f4'ten gecer
   always @(posedge clk) begin
     if ((g0.phase == 3) && (g0.pc == 11'h0f4)) ninstr = ninstr + 1;
     if (mem_wr_en && mem_addr == 16'h29fc) begin
        $display("GLACIAL cycles=%0d instr=%0d cpi=%0d value=%0d",
                 cycle, ninstr, cycle/ninstr, mem_wr_data);
        $finish;
     end
     if (ninstr == 10000 && !seen) begin
        seen = 1;
        $display("GLACIAL 10000 instr in %0d cycles, cpi=%0d",
                 cycle, cycle/10000);
        $finish;
     end
   end

   glacial g0(.clk(clk), .reset(reset), .mem_addr(mem_addr),
              .mem_rd_en(mem_rd_en), .mem_rd_data(mem_rd_data),
              .mem_wr_en(mem_wr_en), .mem_wr_data(mem_wr_data),
              .xint(1'b0), .xtick(1'b0), .uart_tx(uart_tx));
   sram r0(.clk(clk), .addr(mem_addr), .mem_rd_en(mem_rd_en),
           .mem_rd_data(mem_rd_data), .mem_wr_en(mem_wr_en),
           .mem_wr_data(mem_wr_data));
endmodule
