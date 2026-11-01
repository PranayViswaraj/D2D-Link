// tb_top - SystemVerilog UVM smoke test for die_a_top (EDA Playground).
// Die A's AXI4 slave is driven by the UVM AXI master agent. Die A's lanes are connected
// to die_b_top, whose AXI4 master port is served by a simple behavioral memory, so
// end-to-end responses come back across the link.
// EDA Playground: paste uvm_sv/*.sv + rtl/**/*.sv(h), select UVM 1.2, top = tb_top,
// run with +UVM_TESTNAME=d2d_smoke_test.
`timescale 1ns / 1ps
module tb_top;
  import uvm_pkg::*;
  import axi_uvm_pkg::*;

  logic clk_axi_a = 0, clk_axi_b = 0, clk_link = 0, rst_n = 0;
  always #0.85 clk_axi_a = ~clk_axi_a;
  always #1.15 clk_axi_b = ~clk_axi_b;
  always #0.50 clk_link  = ~clk_link;
  initial begin
    repeat (20) @(posedge clk_axi_a);
    rst_n = 1;
  end

  axi_if vif (.aclk(clk_axi_a), .aresetn(rst_n));

  // Die B AXI master signals
  logic [3:0]  m_awid, m_bid, m_arid, m_rid;
  logic [31:0] m_awaddr, m_araddr;
  logic [7:0]  m_awlen, m_arlen, m_wstrb;
  logic [2:0]  m_awsize, m_arsize;
  logic [1:0]  m_awburst, m_arburst, m_bresp, m_rresp;
  logic        m_awvalid, m_awready, m_wlast, m_wvalid, m_wready, m_bvalid, m_bready;
  logic        m_arvalid, m_arready, m_rlast, m_rvalid, m_rready;
  logic [63:0] m_wdata, m_rdata;
  logic [31:0] a2b_data, b2a_data, prdata_a, prdata_b;
  logic        a2b_valid, a2b_sof, b2a_valid, b2a_sof;
  logic        pready_a, pslverr_a, pready_b, pslverr_b, irq_a, irq_b;

  die_a_top u_die_a (
      .clk_axi(clk_axi_a), .rst_axi_n(rst_n), .clk_link(clk_link), .rst_link_n(rst_n),
      .s_axi_awid(vif.awid), .s_axi_awaddr(vif.awaddr), .s_axi_awlen(vif.awlen),
      .s_axi_awsize(vif.awsize), .s_axi_awburst(vif.awburst), .s_axi_awvalid(vif.awvalid),
      .s_axi_awready(vif.awready), .s_axi_wdata(vif.wdata), .s_axi_wstrb(vif.wstrb),
      .s_axi_wlast(vif.wlast), .s_axi_wvalid(vif.wvalid), .s_axi_wready(vif.wready),
      .s_axi_bid(vif.bid), .s_axi_bresp(vif.bresp), .s_axi_bvalid(vif.bvalid),
      .s_axi_bready(vif.bready), .s_axi_arid(vif.arid), .s_axi_araddr(vif.araddr),
      .s_axi_arlen(vif.arlen), .s_axi_arsize(vif.arsize), .s_axi_arburst(vif.arburst),
      .s_axi_arvalid(vif.arvalid), .s_axi_arready(vif.arready), .s_axi_rid(vif.rid),
      .s_axi_rdata(vif.rdata), .s_axi_rresp(vif.rresp), .s_axi_rlast(vif.rlast),
      .s_axi_rvalid(vif.rvalid), .s_axi_rready(vif.rready),
      .apb_psel(1'b0), .apb_penable(1'b0), .apb_pwrite(1'b0), .apb_paddr(8'd0),
      .apb_pwdata(32'd0), .apb_prdata(prdata_a), .apb_pready(pready_a), .apb_pslverr(pslverr_a),
      .irq(irq_a),
      .lane_tx_data(a2b_data), .lane_tx_valid(a2b_valid), .lane_tx_sof(a2b_sof),
      .lane_rx_data(b2a_data), .lane_rx_valid(b2a_valid), .lane_rx_sof(b2a_sof)
  );

  die_b_top u_die_b (
      .clk_axi(clk_axi_b), .rst_axi_n(rst_n), .clk_link(clk_link), .rst_link_n(rst_n),
      .m_axi_awid(m_awid), .m_axi_awaddr(m_awaddr), .m_axi_awlen(m_awlen), .m_axi_awsize(m_awsize),
      .m_axi_awburst(m_awburst), .m_axi_awvalid(m_awvalid), .m_axi_awready(m_awready),
      .m_axi_wdata(m_wdata), .m_axi_wstrb(m_wstrb), .m_axi_wlast(m_wlast), .m_axi_wvalid(m_wvalid),
      .m_axi_wready(m_wready), .m_axi_bid(m_bid), .m_axi_bresp(m_bresp), .m_axi_bvalid(m_bvalid),
      .m_axi_bready(m_bready), .m_axi_arid(m_arid), .m_axi_araddr(m_araddr), .m_axi_arlen(m_arlen),
      .m_axi_arsize(m_arsize), .m_axi_arburst(m_arburst), .m_axi_arvalid(m_arvalid),
      .m_axi_arready(m_arready), .m_axi_rid(m_rid), .m_axi_rdata(m_rdata), .m_axi_rresp(m_rresp),
      .m_axi_rlast(m_rlast), .m_axi_rvalid(m_rvalid), .m_axi_rready(m_rready),
      .apb_psel(1'b0), .apb_penable(1'b0), .apb_pwrite(1'b0), .apb_paddr(8'd0),
      .apb_pwdata(32'd0), .apb_prdata(prdata_b), .apb_pready(pready_b), .apb_pslverr(pslverr_b),
      .irq(irq_b),
      .lane_tx_data(b2a_data), .lane_tx_valid(b2a_valid), .lane_tx_sof(b2a_sof),
      .lane_rx_data(a2b_data), .lane_rx_valid(a2b_valid), .lane_rx_sof(a2b_sof)
  );

  // ---------------- behavioral AXI memory on Die B (one transaction at a time) ----------------
  logic [63:0] mem[logic [31:0]];
  initial begin
    m_awready = 0; m_wready = 0; m_bvalid = 0; m_arready = 0; m_rvalid = 0;
    m_bresp = 0; m_rresp = 0; m_bid = 0; m_rid = 0; m_rdata = 0; m_rlast = 0;
    @(posedge rst_n);
    forever begin
      @(posedge clk_axi_b);
      if (m_awvalid) begin : wr
        logic [31:0] a; logic [3:0] id; int n;
        a = m_awaddr; id = m_awid; n = m_awlen + 1;
        m_awready <= 1; @(posedge clk_axi_b); m_awready <= 0;
        for (int i = 0; i < n; i++) begin
          m_wready <= 1;
          do @(posedge clk_axi_b); while (!m_wvalid);
          for (int b = 0; b < 8; b++)
            if (m_wstrb[b]) begin
              logic [63:0] v;
              v = mem.exists(a + 8 * i) ? mem[a + 8 * i] : 64'h0;
              v[8*b+:8] = m_wdata[8*b+:8];
              mem[a + 8 * i] = v;
            end
        end
        m_wready <= 0;
        m_bid <= id; m_bvalid <= 1;
        do @(posedge clk_axi_b); while (!m_bready);
        m_bvalid <= 0;
      end else if (m_arvalid) begin : rd
        logic [31:0] a; logic [3:0] id; int n;
        a = m_araddr; id = m_arid; n = m_arlen + 1;
        m_arready <= 1; @(posedge clk_axi_b); m_arready <= 0;
        for (int i = 0; i < n; i++) begin
          m_rid <= id; m_rdata <= mem.exists(a + 8 * i) ? mem[a + 8 * i] : 64'h0;
          m_rlast <= (i == n - 1); m_rvalid <= 1;
          do @(posedge clk_axi_b); while (!m_rready);
        end
        m_rvalid <= 0;
      end
    end
  end

  initial begin
    uvm_config_db#(virtual axi_if)::set(null, "*", "vif", vif);
    run_test("d2d_smoke_test");
  end
endmodule
