// sync_2ff - two-flop synchronizer.
// Only used for gray-coded FIFO pointers (at most one bit changes per source clock),
// so a multi-bit instance is safe. Do not use for arbitrary multi-bit buses.
// Ports:
//   clk, rst_n : destination clock / synchronous active-low reset
//   d          : signal from the source domain (must be driven by a source-domain flop)
//   q          : synchronized output
module sync_2ff #(
    parameter integer W = 1
) (
    input  logic         clk,
    input  logic         rst_n,
    input  logic [W-1:0] d,
    output logic [W-1:0] q
);
  logic [W-1:0] meta;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      meta <= '0;
      q    <= '0;
    end else begin
      meta <= d;
      q    <= meta;
    end
  end
endmodule
