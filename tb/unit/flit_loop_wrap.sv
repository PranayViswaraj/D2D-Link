// flit_loop_wrap - unit-test wrapper: flit_tx -> XOR fault -> flit_rx (one clock).
module flit_loop_wrap (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        send_en,
    input  logic        train_mode,
    input  logic        locked,
    input  logic        nak_pending,
    input  logic        rb_valid,
    input  logic [79:0] rb_body,
    input  logic [7:0]  rb_seq,
    input  logic [7:0]  ack_val,
    input  logic [7:0]  cred_req_cum,
    input  logic [7:0]  cred_rsp_cum,
    input  logic        active,
    input  logic [31:0] fi_xor,
    input  logic        req_full,
    input  logic        rsp_full,
    output logic        nak_taken,
    output logic        rb_advance,
    output logic [31:0] lane_data,
    output logic        lane_valid,
    output logic        lane_sof,
    output logic        push_req,
    output logic        push_rsp,
    output logic [79:0] push_body,
    output logic [7:0]  exp_seq,
    output logic        nak_req,
    output logic        bad,
    output logic        nak_rcvd
);
  logic flit_done, train_good, train_locked, nontrain_good, ack_vld;
  logic [7:0] ack_seq, cq, cs;

  flit_tx u_tx (
      .clk(clk), .rst_n(rst_n), .send_en(send_en), .train_mode(train_mode), .locked(locked),
      .nak_pending(nak_pending), .nak_taken(nak_taken), .rb_valid(rb_valid), .rb_body(rb_body),
      .rb_seq(rb_seq), .rb_advance(rb_advance), .ack_val(ack_val), .cred_req_cum(cred_req_cum),
      .cred_rsp_cum(cred_rsp_cum), .lane_data(lane_data), .lane_valid(lane_valid),
      .lane_sof(lane_sof)
  );
  flit_rx u_rx (
      .clk(clk), .rst_n(rst_n), .active(active), .lane_data(lane_data ^ fi_xor),
      .lane_valid(lane_valid), .lane_sof(lane_sof), .push_req(push_req), .push_rsp(push_rsp),
      .push_body(push_body), .req_full(req_full), .rsp_full(rsp_full), .exp_seq(exp_seq),
      .nak_req(nak_req), .flit_done(flit_done), .bad(bad), .train_good(train_good),
      .train_locked(train_locked), .nontrain_good(nontrain_good), .ack_vld(ack_vld),
      .ack_seq(ack_seq), .cred_req_cum(cq), .cred_rsp_cum(cs), .nak_rcvd(nak_rcvd)
  );
endmodule
