`include "d2d_checks.svh"
// async_fifo - dual-clock FIFO with gray-coded pointers (Cummings style).
// First-word-fall-through read: rdata shows the head entry whenever !empty.
// Ports (write domain):
//   wclk, wrst_n : write clock / synchronous active-low reset
//   wr_en, wdata : push (must not be asserted while full)
//   full         : registered full flag
//   wr_rcount    : read pointer as seen in the write domain (binary, AW+1 bits);
//                  monotonically counts entries freed by the reader (lags by 2-3 wclk)
// Ports (read domain):
//   rclk, rrst_n : read clock / synchronous active-low reset
//   rd_en        : pop (must not be asserted while empty)
//   rdata, empty : head entry / registered empty flag
module async_fifo #(
    parameter integer W     = 80,
    parameter integer DEPTH = 8,               // power of 2, >= 4
    parameter integer AW    = $clog2(DEPTH)
) (
    input  logic         wclk,
    input  logic         wrst_n,
    input  logic         wr_en,
    input  logic [W-1:0] wdata,
    output logic         full,
    output logic [AW:0]  wr_rcount,

    input  logic         rclk,
    input  logic         rrst_n,
    input  logic         rd_en,
    output logic [W-1:0] rdata,
    output logic         empty
);
  function automatic logic [AW:0] gray2bin(input logic [AW:0] g);
    logic [AW:0] b;
    b[AW] = g[AW];
    for (int i = AW - 1; i >= 0; i--) b[i] = b[i+1] ^ g[i];
    gray2bin = b;
  endfunction

  // [0:N-1] kept for Yosys 0.33 compatibility
  // verilog_lint: waive unpacked-dimensions-range-ordering
  logic [W-1:0] mem[0:DEPTH-1];

  // ---------------- write domain ----------------
  logic [AW:0] wbin, wgray, wbin_next, wgray_next, wq2_rgray;
  logic        do_wr;

  assign do_wr      = wr_en && !full;
  assign wbin_next  = wbin + {{AW{1'b0}}, do_wr};
  assign wgray_next = (wbin_next >> 1) ^ wbin_next;

  always_ff @(posedge wclk) begin
    if (!wrst_n) begin
      wbin  <= '0;
      wgray <= '0;
      full  <= 1'b0;
    end else begin
      wbin  <= wbin_next;
      wgray <= wgray_next;
      full  <= (wgray_next == {~wq2_rgray[AW:AW-1], wq2_rgray[AW-2:0]});
    end
  end

  always_ff @(posedge wclk) begin
    if (do_wr) mem[wbin[AW-1:0]] <= wdata;
  end

  sync_2ff #(.W(AW + 1)) u_sync_r2w (
      .clk(wclk), .rst_n(wrst_n), .d(rgray), .q(wq2_rgray)
  );
  assign wr_rcount = gray2bin(wq2_rgray);

  // ---------------- read domain ----------------
  logic [AW:0] rbin, rgray, rbin_next, rgray_next, rq2_wgray;
  logic        do_rd;

  assign do_rd      = rd_en && !empty;
  assign rbin_next  = rbin + {{AW{1'b0}}, do_rd};
  assign rgray_next = (rbin_next >> 1) ^ rbin_next;

  always_ff @(posedge rclk) begin
    if (!rrst_n) begin
      rbin  <= '0;
      rgray <= '0;
      empty <= 1'b1;
    end else begin
      rbin  <= rbin_next;
      rgray <= rgray_next;
      empty <= (rgray_next == rq2_wgray);
    end
  end

  assign rdata = mem[rbin[AW-1:0]];

  sync_2ff #(.W(AW + 1)) u_sync_w2r (
      .clk(rclk), .rst_n(rrst_n), .d(wgray), .q(rq2_wgray)
  );

`ifdef FORMAL
  // True occupancy (both domains' binary pointers) never exceeds DEPTH and never
  // underflows; each gray pointer changes by at most one bit per own-clock edge;
  // the (pessimistic) empty flag never claims data that is not there.
  logic [AW:0] f_wg_prev, f_rg_prev, f_occ, f_wd, f_rd;
  always_ff @(posedge wclk) f_wg_prev <= wrst_n ? wgray : '0;
  always_ff @(posedge rclk) f_rg_prev <= rrst_n ? rgray : '0;
  assign f_occ = wbin - rbin;
  assign f_wd  = wgray ^ f_wg_prev;
  assign f_rd  = rgray ^ f_rg_prev;
  always_comb begin
    if (wrst_n && rrst_n) begin
      assert (f_occ <= DEPTH);
      assert ((f_wd & (f_wd - 1'b1)) == '0);
      assert ((f_rd & (f_rd - 1'b1)) == '0);
      if (!empty) assert (f_occ != '0);
    end
  end
`endif

`ifdef SIM
  // Usage contract: callers must never push when full or pop when empty.
  // (Checked in simulation on the real callers; assumed by the formal wrapper.)
  always_ff @(posedge wclk) if (wrst_n) assert (!(wr_en && full));
  always_ff @(posedge rclk) if (rrst_n) assert (!(rd_en && empty));
`endif
endmodule
