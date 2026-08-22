// b2026 fiu v0.1 (20260821)
// Field Isolation Unit: defined-field access in front of conventional
// 32-bit synchronous single-port memory (BSRAM-like, 1-cycle read latency).
//
// Semantics (Wilner 1972, section 7.2): addresses label between-bit
// positions. Forward access of length L at address a covers bits [a, a+L).
// Backward access (fd=1) of length L at address a covers bits [a-L, a),
// delivering the same right-justified field, per the "13 forward from 13
// equals 13 backward from 26" property.
//
// Bit a lives in word a>>5 at position a&31 (LSB-first, little-endian).
//
// Timing: request sampled in IDLE. Read: field registered after 2 memory
// cycles, done on cycle 3. Write: read-modify-write, done on cycle 4.
// On writes, rfield returns the field as it was BEFORE modification
// (the B1700 one-micro swap property).

module fiu (
    input  wire        clk,
    input  wire        rst,
    // request
    input  wire        req,
    input  wire        wr,
    input  wire [23:0] fa,      // bit address
    input  wire [5:0]  len,     // 1..32
    input  wire        fd,      // 0 forward, 1 backward
    input  wire [31:0] wdata,
    output wire        busy,
    output reg         done,
    output reg  [31:0] rfield,
    // memory port, synchronous read, 1-cycle latency
    output reg  [18:0] m_addr,
    output reg         m_re,
    output reg         m_we,
    output reg  [31:0] m_wdata,
    input  wire [31:0] m_rdata
);

    localparam [1:0] IDLE = 2'd0, S1 = 2'd1, S2 = 2'd2, S3 = 2'd3;

    reg [1:0]  state;
    reg [4:0]  off;
    reg [18:0] w0;
    reg        wr_r;
    reg [5:0]  len_r;
    reg [31:0] wd_r;
    reg [31:0] d0;
    reg [31:0] mhi_r;

    wire [23:0] efa = fd ? (fa - {18'b0, len}) : fa;

    // valid during S2: d0 holds mem[w0], m_rdata holds mem[w0+1]
    wire [63:0] pair   = {m_rdata, d0};
    wire [63:0] mask64 = (64'h1 << len_r) - 64'h1;
    wire [63:0] ext    = (pair >> off) & mask64;
    wire [63:0] merged = (pair & ~(mask64 << off))
                       | (({32'h0, wd_r} & mask64) << off);

    assign busy = (state != IDLE);

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            done  <= 1'b0;
        end else begin
            done <= 1'b0;
            case (state)
                IDLE: if (req) begin
                    off   <= efa[4:0];
                    w0    <= efa[23:5];
                    wr_r  <= wr;
                    len_r <= len;
                    wd_r  <= wdata;
                    state <= S1;
                end
                S1: begin
                    d0    <= m_rdata;
                    state <= S2;
                end
                S2: begin
                    rfield <= ext[31:0];       // old field on writes
                    if (wr_r) begin
                        mhi_r <= merged[63:32];
                        state <= S3;
                    end else begin
                        done  <= 1'b1;
                        state <= IDLE;
                    end
                end
                S3: begin
                    done  <= 1'b1;
                    state <= IDLE;
                end
            endcase
        end
    end

    // memory port, Mealy outputs
    always @* begin
        m_addr  = 19'd0;
        m_re    = 1'b0;
        m_we    = 1'b0;
        m_wdata = 32'd0;
        case (state)
            IDLE: if (req) begin
                m_addr = efa[23:5];
                m_re   = 1'b1;
            end
            S1: begin
                m_addr = w0 + 19'd1;
                m_re   = 1'b1;
            end
            S2: if (wr_r) begin
                m_addr  = w0;
                m_we    = 1'b1;
                m_wdata = merged[31:0];
            end
            S3: begin
                m_addr  = w0 + 19'd1;
                m_we    = 1'b1;
                m_wdata = mhi_r;
            end
            default: ;
        endcase
    end

endmodule
