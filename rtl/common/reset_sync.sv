// reset_sync - reset synchronizer: asynchronous assertion, synchronous deassertion.
// This is the only module with an asynchronous reset. Everything downstream uses
// rst_out_n as a synchronous active-low reset.
// Ports:
//   clk       : destination clock
//   rst_in_n  : raw active-low reset (any domain / pad)
//   rst_out_n : synchronized active-low reset for the clk domain
module reset_sync (
    input  logic clk,
    input  logic rst_in_n,
    output logic rst_out_n
);
  logic stage1;

  always_ff @(posedge clk or negedge rst_in_n) begin
    if (!rst_in_n) begin
      stage1    <= 1'b0;
      rst_out_n <= 1'b0;
    end else begin
      stage1    <= 1'b1;
      rst_out_n <= stage1;
    end
  end
endmodule
