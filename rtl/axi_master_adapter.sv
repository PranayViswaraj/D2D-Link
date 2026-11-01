`include "d2d_checks.svh"
// axi_master_adapter - Die B: REQ flit bodies -> AXI4 master; B/R -> RSP flit bodies.
// Executes requests strictly one at a time in arrival order (spec section 5.2):
//   write: AW -> W beats (from REQ_DATA flits) -> wait B -> RSP_HDR
//   read : AR -> forward R beats as RSP_DATA flits until RLAST
// Ports:
//   req_empty/req_rdata/req_rd_en : REQ RX FIFO read side (80-bit flit bodies)
//   rsp_full/rsp_wr_en/rsp_wdata  : RSP TX FIFO write side
//   m_axi_*                       : AXI4 master
module axi_master_adapter (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        req_empty,
    input  logic [79:0] req_rdata,
    output logic        req_rd_en,
    input  logic        rsp_full,
    output logic        rsp_wr_en,
    output logic [79:0] rsp_wdata,
    // AW
    output logic [3:0]  m_axi_awid,
    output logic [31:0] m_axi_awaddr,
    output logic [7:0]  m_axi_awlen,
    output logic [2:0]  m_axi_awsize,
    output logic [1:0]  m_axi_awburst,
    output logic        m_axi_awvalid,
    input  logic        m_axi_awready,
    // W
    output logic [63:0] m_axi_wdata,
    output logic [7:0]  m_axi_wstrb,
    output logic        m_axi_wlast,
    output logic        m_axi_wvalid,
    input  logic        m_axi_wready,
    // B
    input  logic [3:0]  m_axi_bid,
    input  logic [1:0]  m_axi_bresp,
    input  logic        m_axi_bvalid,
    output logic        m_axi_bready,
    // AR
    output logic [3:0]  m_axi_arid,
    output logic [31:0] m_axi_araddr,
    output logic [7:0]  m_axi_arlen,
    output logic [2:0]  m_axi_arsize,
    output logic [1:0]  m_axi_arburst,
    output logic        m_axi_arvalid,
    input  logic        m_axi_arready,
    // R
    input  logic [3:0]  m_axi_rid,
    input  logic [63:0] m_axi_rdata,
    input  logic [1:0]  m_axi_rresp,
    input  logic        m_axi_rlast,
    input  logic        m_axi_rvalid,
    output logic        m_axi_rready
);
  `include "d2d_defs.svh"

  localparam logic [2:0] S_IDLE = 3'd0, S_AW = 3'd1, S_W = 3'd2, S_B = 3'd3, S_AR = 3'd4,
                         S_R = 3'd5;

  logic [2:0]  st;
  logic [3:0]  id, len, beat;
  logic [31:0] addr;
  logic [2:0]  size;
  logic [1:0]  burst;
  logic        is_write, w_hs, b_hs, r_hs;

  // REQ_HDR layout: [71] is_write [70:67] id [66:35] addr [34:31] len [30:28] size [27:26] burst
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      st    <= S_IDLE;
      id    <= 4'd0;
      len   <= 4'd0;
      beat  <= 4'd0;
      addr  <= 32'd0;
      size  <= 3'd0;
      burst <= 2'd0;
    end else begin
      case (st)
        S_IDLE: if (!req_empty) begin
          id    <= req_rdata[70:67];
          addr  <= req_rdata[66:35];
          len   <= req_rdata[34:31];
          size  <= req_rdata[30:28];
          burst <= req_rdata[27:26];
          beat  <= 4'd0;
          st    <= is_write ? S_AW : S_AR;
        end
        S_AW: if (m_axi_awready) st <= S_W;
        S_W: if (w_hs) begin
          beat <= beat + 4'd1;
          if (beat == len) st <= S_B;
        end
        S_B: if (b_hs) st <= S_IDLE;
        S_AR: if (m_axi_arready) st <= S_R;
        S_R: if (r_hs && m_axi_rlast) st <= S_IDLE;
        default: st <= S_IDLE;
      endcase
    end
  end

  assign is_write = req_rdata[71];

  assign m_axi_awid    = id;
  assign m_axi_awaddr  = addr;
  assign m_axi_awlen   = {4'd0, len};
  assign m_axi_awsize  = size;
  assign m_axi_awburst = burst;
  assign m_axi_awvalid = (st == S_AW);

  assign m_axi_wvalid = (st == S_W) && !req_empty;
  assign m_axi_wdata  = req_rdata[71:8];
  assign m_axi_wstrb  = req_rdata[7:0];
  assign m_axi_wlast  = (beat == len);
  assign w_hs         = m_axi_wvalid && m_axi_wready;

  assign m_axi_bready = (st == S_B) && !rsp_full;
  assign b_hs         = m_axi_bvalid && m_axi_bready;

  assign m_axi_arid    = id;
  assign m_axi_araddr  = addr;
  assign m_axi_arlen   = {4'd0, len};
  assign m_axi_arsize  = size;
  assign m_axi_arburst = burst;
  assign m_axi_arvalid = (st == S_AR);

  assign m_axi_rready = (st == S_R) && !rsp_full;
  assign r_hs         = m_axi_rvalid && m_axi_rready;

  assign req_rd_en = ((st == S_IDLE) && !req_empty) || w_hs;

  always_comb begin
    rsp_wr_en = b_hs || r_hs;
    rsp_wdata = 80'd0;
    if (b_hs) begin
      rsp_wdata[79:76] = FT_RSP_HDR;
      rsp_wdata[71:66] = {m_axi_bid, m_axi_bresp};
    end else begin
      rsp_wdata[79:76] = FT_RSP_DATA;
      rsp_wdata[72]    = m_axi_rlast;
      rsp_wdata[71:0]  = {m_axi_rdata, m_axi_rid, m_axi_rresp, 2'b00};
    end
  end


  // Lint waiver (docs/lint_waivers.md): type/flags are only checked by assertions; beat count gives WLAST
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_ok;
  assign unused_ok = ^{req_rdata[79:72]};
  /* verilator lint_on UNUSEDSIGNAL */

`ifdef D2D_CHECKS
  always_ff @(posedge clk) begin
    if (rst_n) begin
      if (st == S_IDLE && !req_empty) assert (req_rdata[79:76] == FT_REQ_HDR);
      if (w_hs) assert (req_rdata[79:76] == FT_REQ_DATA && req_rdata[72] == m_axi_wlast);
    end
  end
`endif
endmodule
