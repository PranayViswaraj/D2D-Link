// die_a_top - Die A: AXI4 slave (host side) + APB CSR + link layer.
// Clock domains: clk_axi (AXI, APB) and clk_link (link layer, lanes). The only
// crossings are the four async FIFOs below (docs/cdc.md, crossings 1-4).
// Ports: s_axi_* AXI4 slave, apb_* APB3 slave, irq, lane_tx_*/lane_rx_* 32-bit lanes.
module die_a_top #(
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
    // AXI4 slave
    input  logic [3:0]  s_axi_awid,
    input  logic [31:0] s_axi_awaddr,
    input  logic [7:0]  s_axi_awlen,
    input  logic [2:0]  s_axi_awsize,
    input  logic [1:0]  s_axi_awburst,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,
    input  logic [63:0] s_axi_wdata,
    input  logic [7:0]  s_axi_wstrb,
    input  logic        s_axi_wlast,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,
    output logic [3:0]  s_axi_bid,
    output logic [1:0]  s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,
    input  logic [3:0]  s_axi_arid,
    input  logic [31:0] s_axi_araddr,
    input  logic [7:0]  s_axi_arlen,
    input  logic [2:0]  s_axi_arsize,
    input  logic [1:0]  s_axi_arburst,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,
    output logic [3:0]  s_axi_rid,
    output logic [63:0] s_axi_rdata,
    output logic [1:0]  s_axi_rresp,
    output logic        s_axi_rlast,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready,
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

  // ---------------- crossing 1: REQ TX (axi -> link) ----------------
  logic        req_full, req_wr_en, req_empty, req_rd_en;
  logic [79:0] req_wdata, req_rdata;
  logic [$clog2(TX_FIFO_DEPTH):0] req_rcount_unused;

  async_fifo #(.W(80), .DEPTH(TX_FIFO_DEPTH)) u_req_tx_fifo (
      .wclk(clk_axi), .wrst_n(ra_n), .wr_en(req_wr_en), .wdata(req_wdata), .full(req_full),
      .wr_rcount(req_rcount_unused),
      .rclk(clk_link), .rrst_n(rl_n), .rd_en(req_rd_en), .rdata(req_rdata), .empty(req_empty)
  );

  // ---------------- crossing 2: RSP RX (link -> axi), RSP credit buffer ----------------
  logic           rsp_wr_en, rsp_full, rsp_empty, rsp_rd_en;
  logic [79:0]    rx_wdata, rsp_rdata;
  logic [RSW-1:0] rsp_rcount;

  async_fifo #(.W(80), .DEPTH(CREDITS_RSP)) u_rsp_rx_fifo (
      .wclk(clk_link), .wrst_n(rl_n), .wr_en(rsp_wr_en), .wdata(rx_wdata), .full(rsp_full),
      .wr_rcount(rsp_rcount),
      .rclk(clk_axi), .rrst_n(ra_n), .rd_en(rsp_rd_en), .rdata(rsp_rdata), .empty(rsp_empty)
  );

  // ---------------- crossings 3/4: CSR config and status ----------------
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
  axi_slave_adapter u_axi (
      .clk(clk_axi), .rst_n(ra_n),
      .s_axi_awid(s_axi_awid), .s_axi_awaddr(s_axi_awaddr), .s_axi_awlen(s_axi_awlen),
      .s_axi_awsize(s_axi_awsize), .s_axi_awburst(s_axi_awburst), .s_axi_awvalid(s_axi_awvalid),
      .s_axi_awready(s_axi_awready),
      .s_axi_wdata(s_axi_wdata), .s_axi_wstrb(s_axi_wstrb), .s_axi_wlast(s_axi_wlast),
      .s_axi_wvalid(s_axi_wvalid), .s_axi_wready(s_axi_wready),
      .s_axi_bid(s_axi_bid), .s_axi_bresp(s_axi_bresp), .s_axi_bvalid(s_axi_bvalid),
      .s_axi_bready(s_axi_bready),
      .s_axi_arid(s_axi_arid), .s_axi_araddr(s_axi_araddr), .s_axi_arlen(s_axi_arlen),
      .s_axi_arsize(s_axi_arsize), .s_axi_arburst(s_axi_arburst), .s_axi_arvalid(s_axi_arvalid),
      .s_axi_arready(s_axi_arready),
      .s_axi_rid(s_axi_rid), .s_axi_rdata(s_axi_rdata), .s_axi_rresp(s_axi_rresp),
      .s_axi_rlast(s_axi_rlast), .s_axi_rvalid(s_axi_rvalid), .s_axi_rready(s_axi_rready),
      .req_full(req_full), .req_wr_en(req_wr_en), .req_wdata(req_wdata),
      .rsp_empty(rsp_empty), .rsp_rdata(rsp_rdata), .rsp_rd_en(rsp_rd_en)
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

  logic rx_req_wr_en_unused, tx_rsp_rd_en_unused;

  link_layer #(
      .REPLAY_DEPTH(REPLAY_DEPTH), .CREDITS_REQ(CREDITS_REQ), .CREDITS_RSP(CREDITS_RSP),
      .REPLAY_TIMEOUT(REPLAY_TIMEOUT), .TRAIN_GOOD(TRAIN_GOOD), .TRAIN_TIMEOUT(TRAIN_TIMEOUT),
      .STABLE_CYCLES(STABLE_CYCLES)
  ) u_link (
      .clk(clk_link), .rst_n(rl_n),
      .enable(enable), .force_retrain(force_retrain), .err_thresh(err_thresh),
      .max_retrain(max_retrain), .err_window(err_window),
      // Die A transmits only on the REQ VC and receives only on the RSP VC
      .tx_req_empty(req_empty), .tx_req_rdata(req_rdata), .tx_req_rd_en(req_rd_en),
      .tx_rsp_empty(1'b1), .tx_rsp_rdata(80'd0), .tx_rsp_rd_en(tx_rsp_rd_en_unused),
      .rx_req_wr_en(rx_req_wr_en_unused), .rx_rsp_wr_en(rsp_wr_en), .rx_wdata(rx_wdata),
      .rx_req_full(1'b1), .rx_rsp_full(rsp_full),
      .rx_req_rcount({RQW{1'b0}}), .rx_rsp_rcount(rsp_rcount),
      .lane_tx_data(lane_tx_data), .lane_tx_valid(lane_tx_valid), .lane_tx_sof(lane_tx_sof),
      .lane_rx_data(lane_rx_data), .lane_rx_valid(lane_rx_valid), .lane_rx_sof(lane_rx_sof),
      .link_state(link_state), .crc_err_cnt(crc_err_cnt), .nak_cnt(nak_cnt),
      .replay_cnt(replay_cnt), .timeout_cnt(timeout_cnt), .retrain_cnt(retrain_cnt)
  );
endmodule
