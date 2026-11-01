// die_b_top - Die B: link layer + AXI4 master (memory side) + APB CSR.
// Clock domains: clk_axi (AXI, APB) and clk_link (link layer, lanes). The only
// crossings are the four async FIFOs below (docs/cdc.md, crossings 5-8).
// Ports: m_axi_* AXI4 master, apb_* APB3 slave, irq, lane_tx_*/lane_rx_* 32-bit lanes.
module die_b_top #(
    parameter integer REPLAY_DEPTH   = 16,
    parameter integer CREDITS_REQ    = 16,
    parameter integer CREDITS_RSP    = 16,
    parameter integer TX_FIFO_DEPTH  = 8,
    parameter integer REPLAY_TIMEOUT = 256,
    parameter integer TRAIN_GOOD     = 8,
    parameter integer TRAIN_TIMEOUT  = 1024,
    parameter integer STABLE_CYCLES  = 2048
) (
    input  logic        clk_axi,
    input  logic        rst_axi_n,
    input  logic        clk_link,
    input  logic        rst_link_n,
    // AXI4 master
    output logic [3:0]  m_axi_awid,
    output logic [31:0] m_axi_awaddr,
    output logic [7:0]  m_axi_awlen,
    output logic [2:0]  m_axi_awsize,
    output logic [1:0]  m_axi_awburst,
    output logic        m_axi_awvalid,
    input  logic        m_axi_awready,
    output logic [63:0] m_axi_wdata,
    output logic [7:0]  m_axi_wstrb,
    output logic        m_axi_wlast,
    output logic        m_axi_wvalid,
    input  logic        m_axi_wready,
    input  logic [3:0]  m_axi_bid,
    input  logic [1:0]  m_axi_bresp,
    input  logic        m_axi_bvalid,
    output logic        m_axi_bready,
    output logic [3:0]  m_axi_arid,
    output logic [31:0] m_axi_araddr,
    output logic [7:0]  m_axi_arlen,
    output logic [2:0]  m_axi_arsize,
    output logic [1:0]  m_axi_arburst,
    output logic        m_axi_arvalid,
    input  logic        m_axi_arready,
    input  logic [3:0]  m_axi_rid,
    input  logic [63:0] m_axi_rdata,
    input  logic [1:0]  m_axi_rresp,
    input  logic        m_axi_rlast,
    input  logic        m_axi_rvalid,
    output logic        m_axi_rready,
    // APB3
    input  logic        apb_psel,
    input  logic        apb_penable,
    input  logic        apb_pwrite,
    input  logic [7:0]  apb_paddr,
    input  logic [31:0] apb_pwdata,
    output logic [31:0] apb_prdata,
    output logic        apb_pready,
    output logic        apb_pslverr,
    output logic        irq,
    // lanes
    output logic [31:0] lane_tx_data,
    output logic        lane_tx_valid,
    output logic        lane_tx_sof,
    input  logic [31:0] lane_rx_data,
    input  logic        lane_rx_valid,
    input  logic        lane_rx_sof
);
  localparam integer RSW = $clog2(CREDITS_RSP) + 1;
  localparam integer RQW = $clog2(CREDITS_REQ) + 1;

  logic ra_n, rl_n;
  reset_sync u_rs_axi (.clk(clk_axi), .rst_in_n(rst_axi_n), .rst_out_n(ra_n));
  reset_sync u_rs_link (.clk(clk_link), .rst_in_n(rst_link_n), .rst_out_n(rl_n));

  // ---------------- crossing 5: REQ RX (link -> axi), REQ credit buffer ----------------
  logic           req_wr_en, req_full, req_empty, req_rd_en;
  logic [79:0]    rx_wdata, req_rdata;
  logic [RQW-1:0] req_rcount;

  async_fifo #(.W(80), .DEPTH(CREDITS_REQ)) u_req_rx_fifo (
      .wclk(clk_link), .wrst_n(rl_n), .wr_en(req_wr_en), .wdata(rx_wdata), .full(req_full),
      .wr_rcount(req_rcount),
      .rclk(clk_axi), .rrst_n(ra_n), .rd_en(req_rd_en), .rdata(req_rdata), .empty(req_empty)
  );

  // ---------------- crossing 6: RSP TX (axi -> link) ----------------
  logic        rsp_full, rsp_wr_en, rsp_empty, rsp_rd_en;
  logic [79:0] rsp_wdata, rsp_rdata;
  logic [$clog2(TX_FIFO_DEPTH):0] rsp_rcount_unused;

  async_fifo #(.W(80), .DEPTH(TX_FIFO_DEPTH)) u_rsp_tx_fifo (
      .wclk(clk_axi), .wrst_n(ra_n), .wr_en(rsp_wr_en), .wdata(rsp_wdata), .full(rsp_full),
      .wr_rcount(rsp_rcount_unused),
      .rclk(clk_link), .rrst_n(rl_n), .rd_en(rsp_rd_en), .rdata(rsp_rdata), .empty(rsp_empty)
  );

  // ---------------- crossings 7/8: CSR config and status ----------------
  logic        cfg_full, cfg_wr_en, cfg_empty, cfg_rd_en;
  logic [29:0] cfg_wdata, cfg_rdata;
  logic        sts_full, sts_wr_en, sts_empty, sts_rd_en;
  logic [82:0] sts_wdata, sts_rdata;
  logic [2:0]  cfg_rcount_unused, sts_rcount_unused;

  async_fifo #(.W(30), .DEPTH(4)) u_cfg_fifo (
      .wclk(clk_axi), .wrst_n(ra_n), .wr_en(cfg_wr_en), .wdata(cfg_wdata), .full(cfg_full),
      .wr_rcount(cfg_rcount_unused),
      .rclk(clk_link), .rrst_n(rl_n), .rd_en(cfg_rd_en), .rdata(cfg_rdata), .empty(cfg_empty)
  );
  async_fifo #(.W(83), .DEPTH(4)) u_sts_fifo (
      .wclk(clk_link), .wrst_n(rl_n), .wr_en(sts_wr_en), .wdata(sts_wdata), .full(sts_full),
      .wr_rcount(sts_rcount_unused),
      .rclk(clk_axi), .rrst_n(ra_n), .rd_en(sts_rd_en), .rdata(sts_rdata), .empty(sts_empty)
  );

  // ---------------- clk_axi domain ----------------
  axi_master_adapter u_axi (
      .clk(clk_axi), .rst_n(ra_n),
      .req_empty(req_empty), .req_rdata(req_rdata), .req_rd_en(req_rd_en),
      .rsp_full(rsp_full), .rsp_wr_en(rsp_wr_en), .rsp_wdata(rsp_wdata),
      .m_axi_awid(m_axi_awid), .m_axi_awaddr(m_axi_awaddr), .m_axi_awlen(m_axi_awlen),
      .m_axi_awsize(m_axi_awsize), .m_axi_awburst(m_axi_awburst), .m_axi_awvalid(m_axi_awvalid),
      .m_axi_awready(m_axi_awready),
      .m_axi_wdata(m_axi_wdata), .m_axi_wstrb(m_axi_wstrb), .m_axi_wlast(m_axi_wlast),
      .m_axi_wvalid(m_axi_wvalid), .m_axi_wready(m_axi_wready),
      .m_axi_bid(m_axi_bid), .m_axi_bresp(m_axi_bresp), .m_axi_bvalid(m_axi_bvalid),
      .m_axi_bready(m_axi_bready),
      .m_axi_arid(m_axi_arid), .m_axi_araddr(m_axi_araddr), .m_axi_arlen(m_axi_arlen),
      .m_axi_arsize(m_axi_arsize), .m_axi_arburst(m_axi_arburst), .m_axi_arvalid(m_axi_arvalid),
      .m_axi_arready(m_axi_arready),
      .m_axi_rid(m_axi_rid), .m_axi_rdata(m_axi_rdata), .m_axi_rresp(m_axi_rresp),
      .m_axi_rlast(m_axi_rlast), .m_axi_rvalid(m_axi_rvalid), .m_axi_rready(m_axi_rready)
  );

  apb_csr u_csr (
      .clk(clk_axi), .rst_n(ra_n),
      .psel(apb_psel), .penable(apb_penable), .pwrite(apb_pwrite), .paddr(apb_paddr),
      .pwdata(apb_pwdata), .prdata(apb_prdata), .pready(apb_pready), .pslverr(apb_pslverr),
      .irq(irq),
      .cfg_full(cfg_full), .cfg_wr_en(cfg_wr_en), .cfg_wdata(cfg_wdata),
      .sts_empty(sts_empty), .sts_rdata(sts_rdata), .sts_rd_en(sts_rd_en)
  );

  // ---------------- clk_link domain ----------------
  logic        enable, force_retrain;
  logic [7:0]  err_thresh;
  logic [3:0]  max_retrain;
  logic [15:0] err_window;
  logic [2:0]  link_state;
  logic [15:0] crc_err_cnt, nak_cnt, replay_cnt, timeout_cnt, retrain_cnt;

  csr_link_sync u_csr_sync (
      .clk(clk_link), .rst_n(rl_n),
      .cfg_empty(cfg_empty), .cfg_rdata(cfg_rdata), .cfg_rd_en(cfg_rd_en),
      .enable(enable), .force_retrain(force_retrain), .err_thresh(err_thresh),
      .max_retrain(max_retrain), .err_window(err_window),
      .link_state(link_state), .crc_err_cnt(crc_err_cnt), .nak_cnt(nak_cnt),
      .replay_cnt(replay_cnt), .timeout_cnt(timeout_cnt), .retrain_cnt(retrain_cnt),
      .sts_full(sts_full), .sts_wr_en(sts_wr_en), .sts_wdata(sts_wdata)
  );

  logic rx_rsp_wr_en_unused, tx_req_rd_en_unused;

  link_layer #(
      .REPLAY_DEPTH(REPLAY_DEPTH), .CREDITS_REQ(CREDITS_REQ), .CREDITS_RSP(CREDITS_RSP),
      .REPLAY_TIMEOUT(REPLAY_TIMEOUT), .TRAIN_GOOD(TRAIN_GOOD), .TRAIN_TIMEOUT(TRAIN_TIMEOUT),
      .STABLE_CYCLES(STABLE_CYCLES)
  ) u_link (
      .clk(clk_link), .rst_n(rl_n),
      .enable(enable), .force_retrain(force_retrain), .err_thresh(err_thresh),
      .max_retrain(max_retrain), .err_window(err_window),
      // Die B transmits only on the RSP VC and receives only on the REQ VC
      .tx_req_empty(1'b1), .tx_req_rdata(80'd0), .tx_req_rd_en(tx_req_rd_en_unused),
      .tx_rsp_empty(rsp_empty), .tx_rsp_rdata(rsp_rdata), .tx_rsp_rd_en(rsp_rd_en),
      .rx_req_wr_en(req_wr_en), .rx_rsp_wr_en(rx_rsp_wr_en_unused), .rx_wdata(rx_wdata),
      .rx_req_full(req_full), .rx_rsp_full(1'b1),
      .rx_req_rcount(req_rcount), .rx_rsp_rcount({RSW{1'b0}}),
      .lane_tx_data(lane_tx_data), .lane_tx_valid(lane_tx_valid), .lane_tx_sof(lane_tx_sof),
      .lane_rx_data(lane_rx_data), .lane_rx_valid(lane_rx_valid), .lane_rx_sof(lane_rx_sof),
      .link_state(link_state), .crc_err_cnt(crc_err_cnt), .nak_cnt(nak_cnt),
      .replay_cnt(replay_cnt), .timeout_cnt(timeout_cnt), .retrain_cnt(retrain_cnt)
  );
endmodule
