`include "d2d_checks.svh"
// credit_counter - transmitter-side credit pool for one virtual channel.
// Resets to MAX (all receiver slots free). consume takes one credit, ret returns
// N credits in the same cycle. The environment guarantees returns never exceed
// credits taken; the bound 0 <= count <= MAX is asserted and formally proven.
// Ports:
//   clk, rst_n : link clock / synchronous active-low reset
//   consume    : take one credit (only when avail)
//   ret        : number of credits returned this cycle
//   count      : current credits
//   avail      : count != 0
module credit_counter #(
    parameter integer MAX = 16,
    parameter integer CW  = $clog2(MAX + 1)
) (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          consume,
    input  logic [7:0]    ret,
    output logic [CW-1:0] count,
    output logic          avail
);
  localparam logic [8:0] MAX9 = MAX[8:0];
  logic [8:0] count9, next9;

  assign count9 = {{(9 - CW) {1'b0}}, count};
  assign next9  = count9 + {1'b0, ret} - {8'd0, consume};
  assign avail  = (count != '0);

  always_ff @(posedge clk) begin
    if (!rst_n) count <= MAX9[CW-1:0];
    else count <= next9[CW-1:0];
  end


  // Lint waiver (docs/lint_waivers.md): upper bits only feed the overflow assertion
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_ok;
  assign unused_ok = ^{next9[8:5]};
  /* verilator lint_on UNUSEDSIGNAL */

`ifdef D2D_CHECKS
  always_ff @(posedge clk) begin
    if (rst_n) begin
      assert (!(consume && !avail));
      assert (next9 <= MAX9);
    end
  end
`endif
endmodule
