// sync_wrap - unit-test wrapper: reset_sync driving a sync_2ff.
module sync_wrap (
    input  logic clk,
    input  logic rst_in_n,
    input  logic d,
    output logic rst_out_n,
    output logic q
);
  reset_sync u_rs (.clk(clk), .rst_in_n(rst_in_n), .rst_out_n(rst_out_n));
  sync_2ff #(.W(1)) u_s (.clk(clk), .rst_n(rst_out_n), .d(d), .q(q));
endmodule
