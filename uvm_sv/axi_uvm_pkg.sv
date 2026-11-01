// axi_uvm_pkg - SystemVerilog UVM AXI4 master agent for D2D-Link Die A:
// seq_item, sequences, driver, monitor, agent, scoreboard, env and smoke test.
// Intended for EDA Playground (any simulator with UVM 1.2); not run locally.
package axi_uvm_pkg;
  import uvm_pkg::*;
  `include "uvm_macros.svh"

  // ------------------------------------------------------------------ item
  class axi_seq_item extends uvm_sequence_item;
    rand bit          is_write;
    rand bit [3:0]    id;
    rand bit [31:0]   addr;
    rand bit [3:0]    len;          // beats - 1 (1..16 beats)
    rand bit [63:0]   data[];
    rand bit [7:0]    strb[];
    bit      [63:0]   rdata[$];
    bit      [1:0]    resp;

    constraint c_align { addr[2:0] == 3'b000; addr < 32'h0001_0000; }
    constraint c_4k    { (addr & 32'hFFF) + 8 * (len + 1) <= 32'h1000; }
    constraint c_size  { data.size() == (is_write ? len + 1 : 0);
                         strb.size() == data.size(); }

    `uvm_object_utils_begin(axi_seq_item)
      `uvm_field_int(is_write, UVM_ALL_ON)
      `uvm_field_int(id, UVM_ALL_ON)
      `uvm_field_int(addr, UVM_ALL_ON | UVM_HEX)
      `uvm_field_int(len, UVM_ALL_ON)
      `uvm_field_array_int(data, UVM_ALL_ON | UVM_HEX)
      `uvm_field_array_int(strb, UVM_ALL_ON | UVM_HEX)
    `uvm_object_utils_end

    function new(string name = "axi_seq_item");
      super.new(name);
    endfunction
  endclass

  // ------------------------------------------------------------------ sequences
  class axi_write_read_seq extends uvm_sequence #(axi_seq_item);
    `uvm_object_utils(axi_write_read_seq)
    rand int unsigned n = 20;
    constraint c_n { n inside {[10:40]}; }

    function new(string name = "axi_write_read_seq");
      super.new(name);
    endfunction

    // each random write is followed by a read-back of the same burst
    task body();
      axi_seq_item wr, rd;
      repeat (n) begin
        wr = axi_seq_item::type_id::create("wr");
        start_item(wr);
        if (!wr.randomize() with { is_write == 1; }) `uvm_fatal("RAND", "write randomize failed")
        finish_item(wr);
        rd = axi_seq_item::type_id::create("rd");
        start_item(rd);
        if (!rd.randomize() with { is_write == 0; addr == wr.addr; len == wr.len; })
          `uvm_fatal("RAND", "read randomize failed")
        finish_item(rd);
      end
    endtask
  endclass

  // ------------------------------------------------------------------ driver
  class axi_master_driver extends uvm_driver #(axi_seq_item);
    `uvm_component_utils(axi_master_driver)
    virtual axi_if vif;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      if (!uvm_config_db#(virtual axi_if)::get(this, "", "vif", vif))
        `uvm_fatal("NOVIF", "virtual interface not set")
    endfunction

    task run_phase(uvm_phase phase);
      vif.drv_cb.awvalid <= 0; vif.drv_cb.wvalid <= 0; vif.drv_cb.arvalid <= 0;
      vif.drv_cb.bready  <= 1; vif.drv_cb.rready <= 1;
      @(posedge vif.aresetn);
      forever begin
        seq_item_port.get_next_item(req);
        if (req.is_write) drive_write(req); else drive_read(req);
        seq_item_port.item_done();
      end
    endtask

    // Responses are collected by the monitor, so the driver can keep up to 4
    // transactions outstanding (the DUT enforces the limit with AWREADY/ARREADY).
    task drive_write(axi_seq_item t);
      @(vif.drv_cb);
      vif.drv_cb.awid <= t.id;  vif.drv_cb.awaddr <= t.addr; vif.drv_cb.awlen <= t.len;
      vif.drv_cb.awsize <= 3'd3; vif.drv_cb.awburst <= 2'b01; vif.drv_cb.awvalid <= 1;
      do @(vif.drv_cb); while (!vif.drv_cb.awready);
      vif.drv_cb.awvalid <= 0;
      foreach (t.data[i]) begin
        vif.drv_cb.wdata <= t.data[i]; vif.drv_cb.wstrb <= t.strb[i];
        vif.drv_cb.wlast <= (i == t.len); vif.drv_cb.wvalid <= 1;
        do @(vif.drv_cb); while (!vif.drv_cb.wready);
      end
      vif.drv_cb.wvalid <= 0;
    endtask

    task drive_read(axi_seq_item t);
      @(vif.drv_cb);
      vif.drv_cb.arid <= t.id;  vif.drv_cb.araddr <= t.addr; vif.drv_cb.arlen <= t.len;
      vif.drv_cb.arsize <= 3'd3; vif.drv_cb.arburst <= 2'b01; vif.drv_cb.arvalid <= 1;
      do @(vif.drv_cb); while (!vif.drv_cb.arready);
      vif.drv_cb.arvalid <= 0;
    endtask
  endclass

  // ------------------------------------------------------------------ monitor
  class axi_monitor extends uvm_monitor;
    `uvm_component_utils(axi_monitor)
    virtual axi_if vif;
    uvm_analysis_port #(axi_seq_item) req_ap;   // completed requests, in acceptance order
    uvm_analysis_port #(axi_seq_item) rsp_ap;   // completed responses

    function new(string name, uvm_component parent);
      super.new(name, parent);
      req_ap = new("req_ap", this);
      rsp_ap = new("rsp_ap", this);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      if (!uvm_config_db#(virtual axi_if)::get(this, "", "vif", vif))
        `uvm_fatal("NOVIF", "virtual interface not set")
    endfunction

    task run_phase(uvm_phase phase);
      axi_seq_item w, r, rr;
      bit [63:0] beats[$];
      bit [63:0] d[$];
      bit [7:0]  s[$];
      forever begin
        @(vif.mon_cb);
        if (vif.mon_cb.awvalid && vif.mon_cb.awready) begin
          w = axi_seq_item::type_id::create("mon_w");
          w.is_write = 1; w.id = vif.mon_cb.awid; w.addr = vif.mon_cb.awaddr;
          w.len = vif.mon_cb.awlen[3:0];
          d.delete(); s.delete();
        end
        if (vif.mon_cb.wvalid && vif.mon_cb.wready) begin
          d.push_back(vif.mon_cb.wdata); s.push_back(vif.mon_cb.wstrb);
          if (vif.mon_cb.wlast) begin
            w.data = d; w.strb = s;
            req_ap.write(w);
          end
        end
        if (vif.mon_cb.arvalid && vif.mon_cb.arready) begin
          r = axi_seq_item::type_id::create("mon_r");
          r.is_write = 0; r.id = vif.mon_cb.arid; r.addr = vif.mon_cb.araddr;
          r.len = vif.mon_cb.arlen[3:0];
          req_ap.write(r);
        end
        if (vif.mon_cb.bvalid && vif.mon_cb.bready) begin
          rr = axi_seq_item::type_id::create("mon_b");
          rr.is_write = 1; rr.id = vif.mon_cb.bid; rr.resp = vif.mon_cb.bresp;
          rsp_ap.write(rr);
        end
        if (vif.mon_cb.rvalid && vif.mon_cb.rready) begin
          beats.push_back(vif.mon_cb.rdata);
          if (vif.mon_cb.rlast) begin
            rr = axi_seq_item::type_id::create("mon_rd");
            rr.is_write = 0; rr.id = vif.mon_cb.rid; rr.resp = vif.mon_cb.rresp;
            rr.rdata = beats;
            beats.delete();
            rsp_ap.write(rr);
          end
        end
      end
    endtask
  endclass

  // ------------------------------------------------------------------ agent
  class axi_master_agent extends uvm_agent;
    `uvm_component_utils(axi_master_agent)
    uvm_sequencer #(axi_seq_item) sqr;
    axi_master_driver             drv;
    axi_monitor                   mon;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      mon = axi_monitor::type_id::create("mon", this);
      if (get_is_active() == UVM_ACTIVE) begin
        sqr = uvm_sequencer#(axi_seq_item)::type_id::create("sqr", this);
        drv = axi_master_driver::type_id::create("drv", this);
      end
    endfunction

    function void connect_phase(uvm_phase phase);
      if (get_is_active() == UVM_ACTIVE) drv.seq_item_port.connect(sqr.seq_item_export);
    endfunction
  endclass

  // ------------------------------------------------------------------ scoreboard
  // Strict in-order execution (spec 5.3) => exact expected-response queue.
  `uvm_analysis_imp_decl(_req)
  `uvm_analysis_imp_decl(_rsp)
  class axi_scoreboard extends uvm_scoreboard;
    `uvm_component_utils(axi_scoreboard)
    uvm_analysis_imp_req #(axi_seq_item, axi_scoreboard) req_imp;
    uvm_analysis_imp_rsp #(axi_seq_item, axi_scoreboard) rsp_imp;
    bit [63:0]   ref_mem[bit [31:0]];
    axi_seq_item expq[$];
    int unsigned n_ok, n_err;

    function new(string name, uvm_component parent);
      super.new(name, parent);
      req_imp = new("req_imp", this);
      rsp_imp = new("rsp_imp", this);
    endfunction

    function bit [63:0] rd_ref(bit [31:0] a);
      return ref_mem.exists(a) ? ref_mem[a] : 64'h0;  // memory model initializes to 0
    endfunction

    function void write_req(axi_seq_item t);
      axi_seq_item e = axi_seq_item::type_id::create("exp");
      e.is_write = t.is_write; e.id = t.id;
      for (int i = 0; i <= t.len; i++) begin
        bit [31:0] a = t.addr + 8 * i;
        if (t.is_write) begin
          bit [63:0] v = rd_ref(a);
          for (int b = 0; b < 8; b++) if (t.strb[i][b]) v[8*b+:8] = t.data[i][8*b+:8];
          ref_mem[a] = v;
        end else e.rdata.push_back(rd_ref(a));
      end
      expq.push_back(e);
    endfunction

    function void write_rsp(axi_seq_item t);
      axi_seq_item e;
      if (expq.size() == 0) begin
        `uvm_error("SB", "response with no outstanding request");
        n_err++;
        return;
      end
      e = expq.pop_front();
      if (e.is_write != t.is_write || e.id != t.id || t.resp != 0 ||
          (!t.is_write && e.rdata != t.rdata)) begin
        `uvm_error("SB", $sformatf("mismatch: exp %s id=%0d got id=%0d", e.is_write ? "B" : "R", e.id, t.id))
        n_err++;
      end else n_ok++;
    endfunction

    function void check_phase(uvm_phase phase);
      if (expq.size() != 0) `uvm_error("SB", $sformatf("%0d transactions never completed", expq.size()))
    endfunction

    function void report_phase(uvm_phase phase);
      `uvm_info("SB", $sformatf("checked %0d responses, %0d errors", n_ok + n_err, n_err), UVM_LOW)
    endfunction
  endclass

  // ------------------------------------------------------------------ env + test
  class d2d_env extends uvm_env;
    `uvm_component_utils(d2d_env)
    axi_master_agent agt;
    axi_scoreboard   sb;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      agt = axi_master_agent::type_id::create("agt", this);
      sb  = axi_scoreboard::type_id::create("sb", this);
    endfunction

    function void connect_phase(uvm_phase phase);
      agt.mon.req_ap.connect(sb.req_imp);
      agt.mon.rsp_ap.connect(sb.rsp_imp);
    endfunction
  endclass

  class d2d_smoke_test extends uvm_test;
    `uvm_component_utils(d2d_smoke_test)
    d2d_env env;

    function new(string name, uvm_component parent);
      super.new(name, parent);
    endfunction

    function void build_phase(uvm_phase phase);
      super.build_phase(phase);
      env = d2d_env::type_id::create("env", this);
    endfunction

    task run_phase(uvm_phase phase);
      axi_write_read_seq seq = axi_write_read_seq::type_id::create("seq");
      phase.raise_objection(this);
      if (!seq.randomize()) `uvm_fatal("RAND", "sequence randomize failed")
      seq.start(env.agt.sqr);
      #20us;  // drain: responses cross the link
      phase.drop_objection(this);
    endtask
  endclass
endpackage
