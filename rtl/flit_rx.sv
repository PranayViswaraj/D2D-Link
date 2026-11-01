`include "d2d_checks.svh"
// flit_rx - lane deserializer, flit check (CRC, legal type, TRAIN pattern),
// in-order sequence acceptance and NAK request generation.
// Ports:
//   active                  : link state is ACTIVE (sequence/ACK/credit processing enabled)
//   lane_*                  : incoming 32-bit lane
//   push_req/push_rsp/body  : in-order sequenced flit body to the RX VC FIFO
//   req_full/rsp_full       : RX VC FIFO full (must never be true on accept: credits)
//   exp_seq                 : next expected sequence number (local ACK value)
//   nak_req                 : pulse, request a NAK (at most one outstanding)
//   flit_done/bad           : a flit (or a framing error) was received / it was bad
//   train_good/train_locked : good TRAIN flit received / its LOCKED flag
//   nontrain_good           : good non-TRAIN flit received
//   ack_vld/ack_seq/cred_*  : piggybacked ACK and credit fields (good, ACTIVE)
//   nak_rcvd                : good NAK received (ACTIVE)
module flit_rx (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        active,
    input  logic [31:0] lane_data,
    input  logic        lane_valid,
    input  logic        lane_sof,
    output logic        push_req,
    output logic        push_rsp,
    output logic [79:0] push_body,
    input  logic        req_full,
    input  logic        rsp_full,
    output logic [7:0]  exp_seq,
    output logic        nak_req,
    output logic        flit_done,
    output logic        bad,
    output logic        train_good,
    output logic        train_locked,
    output logic        nontrain_good,
    output logic        ack_vld,
    output logic [7:0]  ack_seq,
    output logic [7:0]  cred_req_cum,
    output logic [7:0]  cred_rsp_cum,
    output logic        nak_rcvd
);
  `include "d2d_defs.svh"

  // ---------------- deserializer ----------------
  logic [95:0]  sh;
  logic [1:0]   cnt;
  logic         in_frame;
  logic [127:0] fq;
  logic         done_q, ferr_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      sh       <= 96'd0;
      cnt      <= 2'd0;
      in_frame <= 1'b0;
      fq       <= 128'd0;
      done_q   <= 1'b0;
      ferr_q   <= 1'b0;
    end else begin
      done_q <= 1'b0;
      ferr_q <= 1'b0;
      if (lane_valid && lane_sof) begin
        ferr_q     <= in_frame;  // previous flit truncated
        sh[95:64]  <= lane_data;
        cnt        <= 2'd1;
        in_frame   <= 1'b1;
      end else if (lane_valid && in_frame) begin
        case (cnt)
          2'd1: sh[63:32] <= lane_data;
          2'd2: sh[31:0] <= lane_data;
          default: begin
            fq       <= {sh, lane_data};
            done_q   <= 1'b1;
            in_frame <= 1'b0;
          end
        endcase
        cnt <= (cnt == 2'd3) ? 2'd0 : cnt + 2'd1;
      end else if (!lane_valid && in_frame) begin
        ferr_q   <= 1'b1;
        in_frame <= 1'b0;
        cnt      <= 2'd0;
      end
    end
  end

  // ---------------- flit check / decode ----------------
  logic [15:0] crc;
  logic [3:0]  typ;
  logic [7:0]  seq, seq_dist, exp_q;
  logic        crc_ok, legal, good, seqd, is_req, vc_full, in_order, gap, accept, nak_out;

  crc16 #(.N(112)) u_crc (.data(fq[127:16]), .crc(crc));

  assign typ    = fq[127:124];
  assign seq    = fq[123:116];
  assign crc_ok = (crc == fq[15:0]);
  assign legal  = (typ <= FT_TRAIN) && ((typ != FT_TRAIN) || (fq[87:16] == TRAIN_PATTERN));
  assign good   = done_q && crc_ok && legal;

  assign flit_done     = done_q || ferr_q;
  assign bad           = ferr_q || (done_q && !good);
  assign train_good    = good && (typ == FT_TRAIN);
  assign train_locked  = fq[88];
  assign nontrain_good = good && (typ != FT_TRAIN);

  assign ack_vld      = nontrain_good && active;
  assign ack_seq      = fq[115:108];
  assign cred_req_cum = fq[107:100];
  assign cred_rsp_cum = fq[99:92];
  assign nak_rcvd     = ack_vld && (typ == FT_NAK);

  assign seqd     = (typ >= FT_REQ_HDR) && (typ <= FT_RSP_DATA);
  assign is_req   = (typ == FT_REQ_HDR) || (typ == FT_REQ_DATA);
  assign vc_full  = is_req ? req_full : rsp_full;
  assign seq_dist = seq - exp_q;
  assign in_order = ack_vld && seqd && (seq == exp_q);
  assign accept   = in_order && !vc_full;
  // a future seq (gap) means a flit was lost; a full FIFO on accept is a credit bug
  assign gap      = ack_vld && seqd && (seq != exp_q) && (seq_dist < 8'd128);

  assign push_req  = accept && is_req;
  assign push_rsp  = accept && !is_req;
  assign push_body = {fq[127:124], fq[91:88], fq[87:16]};
  assign nak_req   = active && !nak_out && (bad || gap || (in_order && vc_full));
  assign exp_seq   = exp_q;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      exp_q   <= 8'd0;
      nak_out <= 1'b0;
    end else begin
      if (accept) exp_q <= exp_q + 8'd1;
      if (!active || accept) nak_out <= 1'b0;
      else if (nak_req) nak_out <= 1'b1;
    end
  end

`ifdef D2D_CHECKS
  // credits guarantee space for every in-order flit
  always_ff @(posedge clk) if (rst_n) assert (!(in_order && vc_full));
`endif
endmodule
