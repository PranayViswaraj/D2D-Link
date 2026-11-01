`include "d2d_checks.svh"
// axi_slave_adapter - Die A AXI4 slave port -> REQ flit bodies; RSP flit bodies -> B/R.
// One request FSM serializes both channels: an AW followed by all of its W beats, or
// one AR (round-robin between writes and reads), so the global request order is the
// handshake order. Up to MAX_OUT outstanding writes and reads. Responses are returned in
// order from the head of the RSP stream (spec section 5.1).
// Ports:
//   s_axi_*                        : AXI4 slave (64-bit data, 32-bit addr, 4-bit ID)
//   req_full/req_wr_en/req_wdata   : REQ TX FIFO write side (80-bit flit bodies)
//   rsp_empty/rsp_rdata/rsp_rd_en  : RSP RX FIFO read side
module axi_slave_adapter #(
    parameter integer MAX_OUT = 4
) (
    input  logic        clk,
    input  logic        rst_n,
    // AW
    input  logic [3:0]  s_axi_awid,
    input  logic [31:0] s_axi_awaddr,
    input  logic [7:0]  s_axi_awlen,
    input  logic [2:0]  s_axi_awsize,
    input  logic [1:0]  s_axi_awburst,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,
    // W
    input  logic [63:0] s_axi_wdata,
    input  logic [7:0]  s_axi_wstrb,
    input  logic        s_axi_wlast,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,
    // B
    output logic [3:0]  s_axi_bid,
    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,
    // AR
    input  logic [3:0]  s_axi_arid,
    input  logic [31:0] s_axi_araddr,
    input  logic [7:0]  s_axi_arlen,
    input  logic [2:0]  s_axi_arsize,
    input  logic [1:0]  s_axi_arburst,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,
    // R
    output logic [3:0]  s_axi_rid,
    output logic [63:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic        s_axi_rlast,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready,
    // flit FIFOs
    input  logic        req_full,
    output logic        req_wr_en,
    output logic [79:0] req_wdata,
    input  logic        rsp_empty,
    input  logic [79:0] rsp_rdata,
    output logic        rsp_rd_en
);
  `include "d2d_defs.svh"

  localparam integer OW = $clog2(MAX_OUT + 1);
  localparam logic [OW-1:0] MAXO = MAX_OUT[OW-1:0];

  logic          in_wdata, prio_rd;
  logic [3:0]    beats_left;
  logic [OW-1:0] wr_out, rd_out;
  logic          wr_ok, rd_ok, take_aw, take_ar, w_hs, w_last, b_hs, r_hs, r_done;

  // ---------------- request path ----------------
  // READY is gated with the synchronized reset: the pin reset deasserts 2 clocks
  // before rst_n, and a handshake accepted in that window would be lost (bug_log #1).
  assign wr_ok   = rst_n && !in_wdata && s_axi_awvalid && (wr_out != MAXO) && !req_full;
  assign rd_ok   = rst_n && !in_wdata && s_axi_arvalid && (rd_out != MAXO) && !req_full;
  assign take_aw = wr_ok && (!rd_ok || !prio_rd);
  assign take_ar = rd_ok && !take_aw;
  assign s_axi_awready = take_aw;
  assign s_axi_arready = take_ar;
  assign s_axi_wready  = rst_n && in_wdata && !req_full;
  assign w_hs   = s_axi_wvalid && s_axi_wready;
  assign w_last = (beats_left == 4'd0);

  always_comb begin
    req_wr_en = take_aw || take_ar || w_hs;
    req_wdata = 80'd0;
    if (take_aw) begin
      req_wdata[79:76] = FT_REQ_HDR;
      req_wdata[71:0]  = {1'b1, s_axi_awid, s_axi_awaddr, s_axi_awlen[3:0], s_axi_awsize,
                          s_axi_awburst, 26'd0};
    end else if (take_ar) begin
      req_wdata[79:76] = FT_REQ_HDR;
      req_wdata[71:0]  = {1'b0, s_axi_arid, s_axi_araddr, s_axi_arlen[3:0], s_axi_arsize,
                          s_axi_arburst, 26'd0};
    end else begin
      req_wdata[79:76] = FT_REQ_DATA;
      req_wdata[72]    = w_last;
      req_wdata[71:0]  = {s_axi_wdata, s_axi_wstrb};
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      in_wdata   <= 1'b0;
      prio_rd    <= 1'b0;
      beats_left <= 4'd0;
    end else begin
      if (take_aw) begin
        in_wdata   <= 1'b1;
        beats_left <= s_axi_awlen[3:0];
        prio_rd    <= 1'b1;
      end else if (take_ar) begin
        prio_rd <= 1'b0;
      end
      if (w_hs) begin
        if (w_last) in_wdata <= 1'b0;
        else beats_left <= beats_left - 4'd1;
      end
    end
  end

  // ---------------- response path ----------------
  logic [3:0] head_type;
  assign head_type = rsp_rdata[79:76];

  assign s_axi_bvalid = !rsp_empty && (head_type == FT_RSP_HDR);
  assign s_axi_bid    = rsp_rdata[71:68];
  assign s_axi_bresp  = rsp_rdata[67:66];
  assign s_axi_rvalid = !rsp_empty && (head_type == FT_RSP_DATA);
  assign s_axi_rdata  = rsp_rdata[71:8];
  assign s_axi_rid    = rsp_rdata[7:4];
  assign s_axi_rresp  = rsp_rdata[3:2];
  assign s_axi_rlast  = rsp_rdata[72];

  assign b_hs      = s_axi_bvalid && s_axi_bready;
  assign r_hs      = s_axi_rvalid && s_axi_rready;
  assign r_done    = r_hs && s_axi_rlast;
  assign rsp_rd_en = b_hs || r_hs;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_out <= '0;
      rd_out <= '0;
    end else begin
      wr_out <= wr_out + {{(OW - 1) {1'b0}}, take_aw} - {{(OW - 1) {1'b0}}, b_hs};
      rd_out <= rd_out + {{(OW - 1) {1'b0}}, take_ar} - {{(OW - 1) {1'b0}}, r_done};
    end
  end


  // Lint waiver (docs/lint_waivers.md): AxLEN limited to 16 beats (spec 5.3); WLAST is regenerated from the beat counter and only checked by an assertion; reserved RSP bits
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_ok;
  assign unused_ok = ^{s_axi_awlen[7:4], s_axi_arlen[7:4], s_axi_wlast,
                       rsp_rdata[75:73], rsp_rdata[1:0]};
  /* verilator lint_on UNUSEDSIGNAL */

`ifdef D2D_CHECKS
  always_ff @(posedge clk) begin
    if (rst_n) begin
      assert (wr_out <= MAXO && rd_out <= MAXO);
      if (take_aw) assert (s_axi_awlen < 8'd16);
      if (take_ar) assert (s_axi_arlen < 8'd16);
      if (w_hs) assert (s_axi_wlast == w_last);
      // only B/R headers can be at the RSP head
      if (!rsp_empty) assert (head_type == FT_RSP_HDR || head_type == FT_RSP_DATA);
      if (b_hs) assert (wr_out != '0);
      if (r_done) assert (rd_out != '0);
    end
  end
`endif
endmodule
