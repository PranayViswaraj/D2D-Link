// retry_props - reduced Go-Back-N link model: replay_buffer (DEPTH=4) -> lossy channel
// (any flit may be dropped or corrupted) -> receiver sequence check (as flit_rx) and a
// lossy reverse path for cumulative ACK / NAK, plus arbitrary replay timeouts.
// Each flit body carries its own sequence number, so the receiver can check that the
// delivered stream is exactly 0,1,2,... : in order, no loss, no duplication.
module retry_props (
    input logic       clk,
    input logic       rst_n,
    input logic       enq_req,    // free: new flit offered
    input logic       send,       // free: transmitter slot available
    input logic       drop,       // free: channel drops / corrupts the flit
    input logic       ack_ok,     // free: reverse flit carrying ACK arrives intact
    input logic       nak_ok,     // free: a NAK (if requested) arrives intact
    input logic       tmo         // free: replay timer expires (only legal with unacked data)
);
  logic        enq_ready, rd_valid, rd_advance, rewind, ack_progress, rewind_moved, ack_ignored, unacked;
  logic [7:0]  rd_body, rd_seq, wr_seq, ack_seq;
  logic [7:0]  exp_seq, delivered;

  // ---------------- transmitter ----------------
  assign rd_advance = send && rd_valid;

  replay_buffer #(.DEPTH(4), .BW(8)) dut (
      .clk(clk), .rst_n(rst_n), .enq_valid(enq_req), .enq_body(wr_seq), .enq_ready(enq_ready),
      .rd_valid(rd_valid), .rd_body(rd_body), .rd_seq(rd_seq), .rd_advance(rd_advance),
      .ack_valid(ack_ok), .ack_in(exp_seq), .rewind(rewind),
      .wr_seq(wr_seq), .ack_seq(ack_seq), .ack_progress(ack_progress),
      .rewind_moved(rewind_moved), .ack_ignored(ack_ignored), .unacked(unacked)
  );

  // ---------------- channel (1-cycle latency) ----------------
  logic       ch_vld;
  logic [7:0] ch_seq, ch_body;
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      ch_vld <= 1'b0;
      ch_seq <= 8'd0;
      ch_body <= 8'd0;
    end else begin
      ch_vld  <= rd_advance && !drop;
      ch_seq  <= rd_seq;
      ch_body <= rd_body;
    end
  end

  // ---------------- receiver ----------------
  logic       accept, gap, nak_out;
  assign accept = ch_vld && (ch_seq == exp_seq);
  assign gap    = ch_vld && (ch_seq != exp_seq) && ((ch_seq - exp_seq) < 8'd128);
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      exp_seq   <= 8'd0;
      delivered <= 8'd0;
      nak_out   <= 1'b0;
    end else begin
      if (accept) begin
        exp_seq   <= exp_seq + 8'd1;
        delivered <= delivered + 8'd1;
      end
      if (accept) nak_out <= 1'b0;
      else if (gap || (rd_advance && drop)) nak_out <= 1'b1;
    end
  end
  // NAK (with ACK = exp_seq) or timeout rewinds the transmitter
  assign rewind = (nak_out && nak_ok) || (tmo && unacked);

  logic init = 1'b1;
  always_ff @(posedge clk) init <= 1'b0;
  always_comb if (init) assume (!rst_n);

  always_comb begin
    if (!init && rst_n) begin
      if (accept) assert (ch_body == exp_seq);         // in order, no loss, no duplication
      assert (exp_seq == delivered);
      assert ((exp_seq - ack_seq) <= (wr_seq - ack_seq)); // never deliver an unsent flit
      assert (!ack_ignored);                            // receiver ACK always in window
      cover (rewind_moved);
      cover (accept && exp_seq == 8'd6 && rd_seq != wr_seq);
    end
  end

  // cover: a replay occurred and the stream later advanced past the replayed flit
  logic replayed = 1'b0;
  always_ff @(posedge clk) if (rst_n && rewind_moved) replayed <= 1'b1;
  always_comb if (!init && rst_n) cover (replayed && accept && exp_seq == 8'd5);
endmodule
