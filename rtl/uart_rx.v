// b2026 uart_rx v0.1 (20260821)
// Minimal 8N1 receiver. BAUD_DIV = clk cycles per bit (27e6/115200 = 234).
// data/valid hold until ack; a new byte overwrites (host-paced protocol).

module uart_rx #(
    parameter BAUD_DIV = 234
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rxd,
    output reg  [7:0] data,
    output reg        valid,
    input  wire       ack
);
    reg r0 = 1'b1, r1 = 1'b1;
    always @(posedge clk) begin
        r0 <= rxd;
        r1 <= r0;
    end

    localparam [1:0] IDLE = 2'd0, START = 2'd1, BITS = 2'd2, STOP = 2'd3;
    reg [1:0]  state;
    reg [15:0] cnt;
    reg [2:0]  bitn;
    reg [7:0]  sh;

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            valid <= 1'b0;
        end else begin
            if (ack) valid <= 1'b0;
            case (state)
                IDLE: if (!r1) begin
                    cnt   <= BAUD_DIV[15:0] / 2;
                    state <= START;
                end
                START: begin
                    if (cnt == 0) begin
                        if (!r1) begin
                            cnt   <= BAUD_DIV[15:0] - 1;
                            bitn  <= 3'd0;
                            state <= BITS;
                        end else
                            state <= IDLE;      // glitch
                    end else
                        cnt <= cnt - 1'b1;
                end
                BITS: begin
                    if (cnt == 0) begin
                        sh  <= {r1, sh[7:1]};   // LSB first
                        cnt <= BAUD_DIV[15:0] - 1;
                        if (bitn == 3'd7) state <= STOP;
                        bitn <= bitn + 1'b1;
                    end else
                        cnt <= cnt - 1'b1;
                end
                STOP: begin
                    if (cnt == 0) begin
                        data  <= sh;
                        valid <= 1'b1;
                        state <= IDLE;
                    end else
                        cnt <= cnt - 1'b1;
                end
            endcase
        end
    end
endmodule
