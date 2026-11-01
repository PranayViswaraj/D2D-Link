// axi_if - AXI4 interface (64-bit data, 32-bit address, 4-bit ID) with clocking
// blocks for the UVM master driver and monitor.
interface axi_if (input logic aclk, input logic aresetn);
  logic [3:0]  awid;    logic [31:0] awaddr;  logic [7:0] awlen;  logic [2:0] awsize;
  logic [1:0]  awburst; logic        awvalid; logic       awready;
  logic [63:0] wdata;   logic [7:0]  wstrb;   logic       wlast;  logic       wvalid;
  logic        wready;
  logic [3:0]  bid;     logic [1:0]  bresp;   logic       bvalid; logic       bready;
  logic [3:0]  arid;    logic [31:0] araddr;  logic [7:0] arlen;  logic [2:0] arsize;
  logic [1:0]  arburst; logic        arvalid; logic       arready;
  logic [3:0]  rid;     logic [63:0] rdata;   logic [1:0] rresp;  logic       rlast;
  logic        rvalid;  logic        rready;

  clocking drv_cb @(posedge aclk);
    default input #1step output #1;
    output awid, awaddr, awlen, awsize, awburst, awvalid, wdata, wstrb, wlast, wvalid, bready,
           arid, araddr, arlen, arsize, arburst, arvalid, rready;
    input  awready, wready, bid, bresp, bvalid, arready, rid, rdata, rresp, rlast, rvalid;
  endclocking

  clocking mon_cb @(posedge aclk);
    default input #1step;
    input awid, awaddr, awlen, awvalid, awready, wdata, wstrb, wlast, wvalid, wready,
          bid, bresp, bvalid, bready, arid, araddr, arlen, arvalid, arready,
          rid, rdata, rresp, rlast, rvalid, rready;
  endclocking
endinterface
