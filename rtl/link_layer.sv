`include "d2d_checks.svh"
// link_layer - one die's link layer (clk_link domain): TX + RX for both virtual channels.
// Integrates the VC enqueue arbiter, per-VC credit counters, replay buffer, flit_tx,
// flit_rx, training FSM, replay timer and error counters.
// Ports:
//   enable, force_retrain, err_*      : configuration (from csr_link_sync)
//   tx_{req,rsp}_{empty,rdata,rd_en}  : read side of the TX VC CDC FIFOs (flit bodies)
//   rx_{req,rsp}_{wr_en,wdata,full}   : write side of the RX VC CDC FIFOs (= credit buffers)
//   rx_{req,rsp}_rcount               : RX FIFO read pointer seen in clk_link (credit return)
//   lane_tx_*, lane_rx_*              : 32-bit lanes
//   link_state, *_cnt                 : status for CSR snapshot (16-bit saturating counters)
module link_layer #(
    parameter integer REPLAY_DEPTH   = 16,
    parameter integer CREDITS_REQ    = 16,
    parameter integer CREDITS_RSP    = 16,
    parameter integer REPLAY_TIMEOUT = 256,
    parameter integer TRAIN_GOOD     = 8,
    parameter integer TRAIN_TIMEOUT  = 1024,
    parameter integer STABLE_CYCLES  = 2048,
    parameter integer RQW            = $clog2(CREDITS_REQ) + 1,
    parameter integer RSW            = $clog2(CREDITS_RSP) + 1
) (
    input  logic           clk,
    input  logic           rst_n,
    // configuration
    input  logic           enable,
    input  logic           force_retrain,
    input  logic [7:0]     err_thresh,
    input  logic [3:0]     max_retrain,
    input  logic [15:0]    err_window,
    // TX VC FIFOs (read side)
    input  logic           tx_req_empty,
    input  logic [79:0]    tx_req_rdata,
    output logic           tx_req_rd_en,
    input  logic           tx_rsp_empty,
    input  logic [79:0]    tx_rsp_rdata,
    output logic           tx_rsp_rd_en,
    // RX VC FIFOs (write side)
    output logic           rx_req_wr_en,
    output logic           rx_rsp_wr_en,
    output logic [79:0]    rx_wdata,
    input  logic           rx_req_full,
    input  logic           rx_rsp_full,
    input  logic [RQW-1:0] rx_req_rcount,
    input  logic [RSW-1:0] rx_rsp_rcount,
    // lanes
    output logic [31:0]    lane_tx_data,
    output logic           lane_tx_valid,
    output logic           lane_tx_sof,
    input  logic [31:0]    lane_rx_data,
    input  logic           lane_rx_valid,
    input  logic           lane_rx_sof,
    // status
    output logic [2:0]     link_state,
    output logic [15:0]    crc_err_cnt,
    output logic [15:0]    nak_cnt,
    output logic [15:0]    replay_cnt,
    output logic [15:0]    timeout_cnt,
    output logic [15:0]    retrain_cnt
);
  `include "d2d_defs.svh"

  localparam integer TMW = $clog2(REPLAY_TIMEOUT + 1);
  localparam logic [TMW-1:0] RTMO = REPLAY_TIMEOUT[TMW-1:0];

  // ---------------- receive path ----------------
  logic       active, send_en, train_mode, locked, enter_active, retrain_pulse;
  logic [7:0] exp_seq, rx_ack_seq, rx_cq_cum, rx_cs_cum;
  logic       nak_req, flit_done, bad, train_good, train_locked, nontrain_good;
  logic       ack_vld, nak_rcvd;

  flit_rx u_rx (
      .clk(clk), .rst_n(rst_n), .active(active),
      .lane_data(lane_rx_data), .lane_valid(lane_rx_valid), .lane_sof(lane_rx_sof),
      .push_req(rx_req_wr_en), .push_rsp(rx_rsp_wr_en), .push_body(rx_wdata),
      .req_full(rx_req_full), .rsp_full(rx_rsp_full),
      .exp_seq(exp_seq), .nak_req(nak_req),
      .flit_done(flit_done), .bad(bad), .train_good(train_good), .train_locked(train_locked),
      .nontrain_good(nontrain_good), .ack_vld(ack_vld), .ack_seq(rx_ack_seq),
      .cred_req_cum(rx_cq_cum), .cred_rsp_cum(rx_cs_cum), .nak_rcvd(nak_rcvd)
  );

  link_training_fsm #(
      .TRAIN_GOOD(TRAIN_GOOD), .TRAIN_TIMEOUT(TRAIN_TIMEOUT), .STABLE_CYCLES(STABLE_CYCLES)
  ) u_fsm (
      .clk(clk), .rst_n(rst_n), .enable(enable), .force_retrain(force_retrain),
      .err_thresh(err_thresh), .max_retrain(max_retrain), .err_window(err_window),
      .flit_done(flit_done), .bad(bad), .train_good(train_good), .train_locked(train_locked),
      .nontrain_good(nontrain_good), .state(link_state), .locked(locked),
      .enter_active(enter_active), .retrain_pulse(retrain_pulse)
  );

  assign active     = (link_state == ST_ACTIVE);
  assign train_mode = (link_state == ST_TRAIN) || (link_state == ST_RETRAIN);
  assign send_en    = active || train_mode;

  // ---------------- freed-credit accumulators (local receiver) ----------------
  logic [RQW-1:0] rq_rc_q;
  logic [RSW-1:0] rs_rc_q;
  logic [7:0]     freed_req_cum, freed_rsp_cum;
  logic [RQW-1:0] rq_delta;
  logic [RSW-1:0] rs_delta;

  assign rq_delta = rx_req_rcount - rq_rc_q;
  assign rs_delta = rx_rsp_rcount - rs_rc_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      rq_rc_q       <= '0;
      rs_rc_q       <= '0;
      freed_req_cum <= 8'd0;
      freed_rsp_cum <= 8'd0;
    end else begin
      rq_rc_q       <= rx_req_rcount;
      rs_rc_q       <= rx_rsp_rcount;
      freed_req_cum <= freed_req_cum + {{(8 - RQW) {1'b0}}, rq_delta};
      freed_rsp_cum <= freed_rsp_cum + {{(8 - RSW) {1'b0}}, rs_delta};
    end
  end

  // ---------------- transmit credits (remote receiver) ----------------
  logic [7:0] last_cq_cum, last_cs_cum, ret_req, ret_rsp;
  logic       cq_avail, cs_avail, enq_req, enq_rsp;
  logic [$clog2(CREDITS_REQ + 1)-1:0] cq_count;
  logic [$clog2(CREDITS_RSP + 1)-1:0] cs_count;

  assign ret_req = ack_vld ? (rx_cq_cum - last_cq_cum) : 8'd0;
  assign ret_rsp = ack_vld ? (rx_cs_cum - last_cs_cum) : 8'd0;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      last_cq_cum <= 8'd0;
      last_cs_cum <= 8'd0;
    end else if (ack_vld) begin
      last_cq_cum <= rx_cq_cum;
      last_cs_cum <= rx_cs_cum;
    end
  end

  credit_counter #(.MAX(CREDITS_REQ)) u_cc_req (
      .clk(clk), .rst_n(rst_n), .consume(enq_req), .ret(ret_req),
      .count(cq_count), .avail(cq_avail)
  );
  credit_counter #(.MAX(CREDITS_RSP)) u_cc_rsp (
      .clk(clk), .rst_n(rst_n), .consume(enq_rsp), .ret(ret_rsp),
      .count(cs_count), .avail(cs_avail)
  );

  // ---------------- VC enqueue arbiter (round robin) ----------------
  logic       rb_enq_ready, cand_req, cand_rsp, rr_rsp, enq_ok;
  logic [79:0] enq_body;

  assign enq_ok   = rb_enq_ready && (link_state != ST_RESET) && (link_state != ST_FAILED);
  assign cand_req = enq_ok && !tx_req_empty && cq_avail;
  assign cand_rsp = enq_ok && !tx_rsp_empty && cs_avail;
  assign enq_rsp  = cand_rsp && (rr_rsp || !cand_req);
  assign enq_req  = cand_req && !enq_rsp;
  assign enq_body = enq_rsp ? tx_rsp_rdata : tx_req_rdata;
  assign tx_req_rd_en = enq_req;
  assign tx_rsp_rd_en = enq_rsp;

  always_ff @(posedge clk) begin
    if (!rst_n) rr_rsp <= 1'b0;
    else if (enq_req) rr_rsp <= 1'b1;
    else if (enq_rsp) rr_rsp <= 1'b0;
  end

  // ---------------- replay buffer + timer ----------------
  logic        rb_valid, rb_advance, rewind, ack_progress, rewind_moved, ack_ignored, unacked;
  logic [79:0] rb_body;
  logic [7:0]  rb_seq, wr_seq, ack_ptr;
  logic [TMW-1:0] rtmr;
  logic        replay_timeout;

  assign replay_timeout = active && unacked && (rtmr == RTMO);
  assign rewind         = nak_rcvd || replay_timeout || enter_active;

  replay_buffer #(.DEPTH(REPLAY_DEPTH), .BW(80)) u_rb (
      .clk(clk), .rst_n(rst_n),
      .enq_valid(enq_req || enq_rsp), .enq_body(enq_body), .enq_ready(rb_enq_ready),
      .rd_valid(rb_valid), .rd_body(rb_body), .rd_seq(rb_seq), .rd_advance(rb_advance),
      .ack_valid(ack_vld), .ack_in(rx_ack_seq), .rewind(rewind),
      .wr_seq(wr_seq), .ack_seq(ack_ptr), .ack_progress(ack_progress),
      .rewind_moved(rewind_moved), .ack_ignored(ack_ignored), .unacked(unacked)
  );

  always_ff @(posedge clk) begin
    if (!rst_n) rtmr <= '0;
    else if (!active || !unacked || ack_progress || rewind) rtmr <= '0;
    else if (rtmr != RTMO) rtmr <= rtmr + 1'b1;
  end

  // ---------------- transmitter ----------------
  logic nak_pending, nak_taken;

  always_ff @(posedge clk) begin
    if (!rst_n) nak_pending <= 1'b0;
    else if (!active) nak_pending <= 1'b0;
    else if (nak_req) nak_pending <= 1'b1;
    else if (nak_taken) nak_pending <= 1'b0;
  end

  flit_tx u_tx (
      .clk(clk), .rst_n(rst_n), .send_en(send_en), .train_mode(train_mode), .locked(locked),
      .nak_pending(nak_pending && active), .nak_taken(nak_taken),
      .rb_valid(rb_valid && active), .rb_body(rb_body), .rb_seq(rb_seq), .rb_advance(rb_advance),
      .ack_val(exp_seq), .cred_req_cum(freed_req_cum), .cred_rsp_cum(freed_rsp_cum),
      .lane_data(lane_tx_data), .lane_valid(lane_tx_valid), .lane_sof(lane_tx_sof)
  );

  // ---------------- error counters (16-bit saturating) ----------------
  function automatic logic [15:0] sat_inc(input logic [15:0] v, input logic inc);
    sat_inc = (inc && v != 16'hFFFF) ? v + 16'd1 : v;
  endfunction

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      crc_err_cnt <= 16'd0;
      nak_cnt     <= 16'd0;
      replay_cnt  <= 16'd0;
      timeout_cnt <= 16'd0;
      retrain_cnt <= 16'd0;
    end else begin
      crc_err_cnt <= sat_inc(crc_err_cnt, bad);
      nak_cnt     <= sat_inc(nak_cnt, nak_taken);
      replay_cnt  <= sat_inc(replay_cnt, rewind_moved);
      timeout_cnt <= sat_inc(timeout_cnt, replay_timeout);
      retrain_cnt <= sat_inc(retrain_cnt, retrain_pulse);
    end
  end


  // Lint waiver (docs/lint_waivers.md): credit levels / pointers kept for debug visibility; ack_ignored feeds an assertion
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_ok;
  assign unused_ok = ^{cq_count, cs_count, ack_ignored, wr_seq, ack_ptr};
  /* verilator lint_on UNUSEDSIGNAL */

`ifdef D2D_CHECKS
  always_ff @(posedge clk) begin
    if (rst_n) begin
      assert (!ack_ignored);  // peer never ACKs beyond what was sent
      assert (!(enq_req && enq_rsp));
    end
  end
`endif
endmodule
