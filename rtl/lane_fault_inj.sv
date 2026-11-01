// lane_fault_inj - lane channel model with fault injection (verification top only).
// One register stage (channel latency). Faults are applied per beat:
//   fi_xor  : XORed into the lane data (bit flips, beat corruption, burst errors)
//   fi_drop : suppresses valid/sof for this beat (hold for 4 beats to drop a flit)
// Tie fi_xor/fi_drop to 0 for a fault-free channel.
module lane_fault_inj (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [31:0] in_data,
    input  logic        in_valid,
    input  logic        in_sof,
    input  logic [31:0] fi_xor,
    input  logic        fi_drop,
    output logic [31:0] out_data,
    output logic        out_valid,
    output logic        out_sof
);
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      out_data  <= 32'd0;
      out_valid <= 1'b0;
      out_sof   <= 1'b0;
    end else begin
      out_data  <= in_data ^ fi_xor;
      out_valid <= in_valid && !fi_drop;
      out_sof   <= in_sof && !fi_drop;
    end
  end
endmodule
