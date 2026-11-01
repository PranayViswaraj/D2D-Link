// fifo_props - formal wrapper for async_fifo (DEPTH=4, W=4) with two unconstrained,
// unrelated clocks (sby multiclock). The occupancy / gray-code properties live inside
// async_fifo (`ifdef FORMAL`); this wrapper supplies the reset environment and the
// usage contract, and checks data ordering: every popped word is the oldest pushed
// word (each word carries its write index), i.e. no loss, duplication or reordering.
module fifo_props (
    input logic wclk,
    input logic rclk,
    input logic wrst_n,
    input logic rrst_n,
    input logic wr_en,
    input logic rd_en
);
  logic       full, empty;
  logic [3:0] rdata, wtag, rtag;
  logic [2:0] wr_rcount;

  async_fifo #(.W(4), .DEPTH(4)) dut (
      .wclk(wclk), .wrst_n(wrst_n), .wr_en(wr_en), .wdata(wtag), .full(full), .wr_rcount(wr_rcount),
      .rclk(rclk), .rrst_n(rrst_n), .rd_en(rd_en), .rdata(rdata), .empty(empty)
  );

  always_ff @(posedge wclk) if (!wrst_n) wtag <= 4'd0; else if (wr_en && !full) wtag <= wtag + 4'd1;
  always_ff @(posedge rclk) if (!rrst_n) rtag <= 4'd0; else if (rd_en && !empty) rtag <= rtag + 4'd1;

  // Reset environment: both domains see a reset edge before either deasserts, and the
  // resets never re-assert afterwards (formal-only initial values are allowed here).
  logic w_seen = 1'b0, r_seen = 1'b0, w_rel = 1'b0, r_rel = 1'b0;
  always_ff @(posedge wclk) begin
    if (!wrst_n) w_seen <= 1'b1;
    if (wrst_n) w_rel <= 1'b1;
  end
  always_ff @(posedge rclk) begin
    if (!rrst_n) r_seen <= 1'b1;
    if (rrst_n) r_rel <= 1'b1;
  end
  always_comb begin
    if (!(w_seen && r_seen)) assume (!wrst_n && !rrst_n);
    if (w_rel) assume (wrst_n);
    if (r_rel) assume (rrst_n);
  end

  always_comb begin
    if (wrst_n && rrst_n) begin
      if (!empty) assert (rdata == rtag);
      cover (full);
      cover (full && rd_en);
    end
  end
endmodule
