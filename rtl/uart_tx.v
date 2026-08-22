// b2026 uart_tx v0.1 (20260821)
// Minimal 8N1 transmitter. BAUD_DIV = clk cycles per bit.

module uart_tx #(
    parameter BAUD_DIV = 234
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       we,
    input  wire [7:0] data,
    output reg        txd,
    output wire       busy
);
    reg [9:0]  sh;      // stop, data[7:0], start
    reg [3:0]  bitn;
    reg [15:0] cnt;
    reg        run;

    assign busy = run;

    always @(posedge clk) begin
        if (rst) begin
            txd <= 1'b1;
            run <= 1'b0;
        end else if (!run) begin
            txd <= 1'b1;
            if (we) begin
                sh   <= {1'b1, data, 1'b0};
                bitn <= 4'd0;
                cnt  <= BAUD_DIV[15:0] - 1;
                run  <= 1'b1;
                txd  <= 1'b0;             // start bit now
            end
        end else begin
            if (cnt == 0) begin
                if (bitn == 4'd9) begin
                    run <= 1'b0;
                    txd <= 1'b1;
                end else begin
                    bitn <= bitn + 1'b1;
                    txd  <= sh[bitn + 1];
                    cnt  <= BAUD_DIV[15:0] - 1;
                end
            end else
                cnt <= cnt - 1'b1;
        end
    end
endmodule
