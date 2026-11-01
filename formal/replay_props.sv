// replay_props - replay_buffer (DEPTH=4) with unconstrained enqueue / transmit / ACK /
// rewind inputs, starting from reset. The pointer invariants are the assertions embedded
// in replay_buffer (ack <= rd <= wr, wr - ack <= DEPTH); here we add that a full buffer
// never accepts and that rewinds stay inside the window.
module replay_props (
    input logic       clk,
    input logic       rst_n,
    input logic       enq_valid,
    input logic [3:0] enq_body,
    input logic       rd_advance,
    input logic       ack_valid,
    input logic [7:0] ack_in,
    input logic       rewind
);
  logic       enq_ready, rd_valid, ack_progress, rewind_moved, ack_ignored, unacked;
  logic [3:0] rd_body;
  logic [7:0] rd_seq, wr_seq, ack_seq;

  replay_buffer #(.DEPTH(4), .BW(4)) dut (
      .clk(clk), .rst_n(rst_n), .enq_valid(enq_valid), .enq_body(enq_body), .enq_ready(enq_ready),
      .rd_valid(rd_valid), .rd_body(rd_body), .rd_seq(rd_seq), .rd_advance(rd_advance),
      .ack_valid(ack_valid), .ack_in(ack_in), .rewind(rewind), .wr_seq(wr_seq), .ack_seq(ack_seq),
      .ack_progress(ack_progress), .rewind_moved(rewind_moved), .ack_ignored(ack_ignored),
      .unacked(unacked)
  );

  logic init = 1'b1;
  logic [7:0] wr_prev = 8'd0;
  logic       full_prev = 1'b0, enq_prev = 1'b0, rew_prev = 1'b0, run_prev = 1'b0;
  always_ff @(posedge clk) begin
    init      <= 1'b0;
    wr_prev   <= wr_seq;
    full_prev <= !enq_ready;
    enq_prev  <= enq_valid;
    rew_prev  <= rewind;
    run_prev  <= rst_n;
  end
  always_comb if (init) assume (!rst_n);

  always_comb begin
    if (!init && rst_n) begin
      assert ((wr_seq - ack_seq) <= 8'd4);
      assert ((rd_seq - ack_seq) <= (wr_seq - ack_seq));
      if (run_prev && full_prev && enq_prev) assert (wr_seq == wr_prev);  // full never accepts
      if (run_prev && rew_prev) assert (rd_seq == ack_seq);               // rewind lands on oldest unacked
      cover (!enq_ready && rewind_moved);
    end
  end
endmodule
