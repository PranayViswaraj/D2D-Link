`include "d2d_checks.svh"
// flit_tx - flit selection, header insertion, CRC generation and 4-beat serializer.
// At every flit boundary the next flit is chosen by priority:
//   TRAIN (while training) > NAK > replay buffer entry at rd_seq > ACK > CREDIT > IDLE.
// ACK_SEQ and credit fields are filled at send time, so replayed flits carry fresh values.
// Ports:
//   send_en        : link is in TRAIN/RETRAIN/ACTIVE (lane driven)
//   train_mode     : send TRAIN flits; locked = LOCKED flag to advertise
//   nak_pending    : a NAK must be sent; nak_taken pulses when it is loaded
//   rb_*           : replay buffer read port; rb_advance pulses when rb_seq is loaded
//   ack_val        : local receiver's next expected seq (piggybacked ACK)
//   cred_*_cum     : local receiver's cumulative freed-slot counts per VC
//   lane_*         : 32-bit lane, beat 0 (bits 127:96) flagged with lane_sof
module flit_tx (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        send_en,
    input  logic        train_mode,
    input  logic        locked,
    input  logic        nak_pending,
    output logic        nak_taken,
    input  logic        rb_valid,
    input  logic [79:0] rb_body,
    input  logic [7:0]  rb_seq,
    output logic        rb_advance,
    input  logic [7:0]  ack_val,
    input  logic [7:0]  cred_req_cum,
    input  logic [7:0]  cred_rsp_cum,
    output logic [31:0] lane_data,
    output logic        lane_valid,
    output logic        lane_sof
);
  `include "d2d_defs.svh"

  logic [127:0] flit_q;
  logic [1:0]   beat;
  logic         busy, load;
  logic [7:0]   last_ack, last_cq, last_cs;

  logic [3:0]   typ, flags;
  logic [7:0]   seq, ackf, cqf, csf;
  logic [71:0]  payload;
  logic [111:0] hdr;
  logic [15:0]  crc;

  assign load = send_en && (!busy || (beat == 2'd3));

  always_comb begin
    nak_taken  = 1'b0;
    rb_advance = 1'b0;
    seq        = 8'd0;
    ackf       = ack_val;
    cqf        = cred_req_cum;
    csf        = cred_rsp_cum;
    flags      = 4'd0;
    payload    = 72'd0;
    if (train_mode) begin
      typ     = FT_TRAIN;
      flags   = {3'b000, locked};
      payload = TRAIN_PATTERN;
      ackf    = 8'd0;
      cqf     = 8'd0;
      csf     = 8'd0;
    end else if (nak_pending) begin
      typ       = FT_NAK;
      nak_taken = load;
    end else if (rb_valid) begin
      typ        = rb_body[79:76];
      flags      = rb_body[75:72];
      payload    = rb_body[71:0];
      seq        = rb_seq;
      rb_advance = load;
    end else if (ack_val != last_ack) begin
      typ = FT_ACK;
    end else if ((cred_req_cum != last_cq) || (cred_rsp_cum != last_cs)) begin
      typ = FT_CREDIT;
    end else begin
      typ = FT_IDLE;
    end
  end

  assign hdr = {typ, seq, ackf, cqf, csf, flags, payload};

  crc16 #(.N(112)) u_crc (.data(hdr), .crc(crc));

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      flit_q   <= 128'd0;
      beat     <= 2'd0;
      busy     <= 1'b0;
      last_ack <= 8'd0;
      last_cq  <= 8'd0;
      last_cs  <= 8'd0;
    end else if (busy && (beat != 2'd3)) begin
      beat <= beat + 2'd1;
    end else if (send_en) begin
      flit_q <= {hdr, crc};
      beat   <= 2'd0;
      busy   <= 1'b1;
      if (!train_mode) begin
        last_ack <= ack_val;
        last_cq  <= cred_req_cum;
        last_cs  <= cred_rsp_cum;
      end
    end else begin
      busy <= 1'b0;
    end
  end

  always_comb begin
    case (beat)
      2'd0:    lane_data = flit_q[127:96];
      2'd1:    lane_data = flit_q[95:64];
      2'd2:    lane_data = flit_q[63:32];
      default: lane_data = flit_q[31:0];
    endcase
  end
  assign lane_valid = busy;
  assign lane_sof   = busy && (beat == 2'd0);

`ifdef D2D_CHECKS
  // replay-buffer bodies must be sequenced types
  always_ff @(posedge clk) begin
    if (rst_n && rb_advance) assert (rb_body[79:76] >= FT_REQ_HDR && rb_body[79:76] <= FT_RSP_DATA);
  end
`endif
endmodule
