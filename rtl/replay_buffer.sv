`include "d2d_checks.svh"
// replay_buffer - Go-Back-N retransmission store for sequenced flits.
// Three 8-bit sequence pointers, compared with mod-256 distances from ack_seq:
//   ack_seq : oldest unacknowledged flit
//   rd_seq  : next flit to (re)transmit
//   wr_seq  : next sequence number to assign
// Invariant: ack_seq <= rd_seq <= wr_seq and wr_seq - ack_seq <= DEPTH.
// Ports:
//   enq_valid/enq_body/enq_ready : append a flit body (assigned SEQ = wr_seq)
//   rd_valid/rd_body/rd_seq      : flit at rd_seq (valid when rd_seq != wr_seq)
//   rd_advance                   : the transmitter has sent rd_seq
//   ack_valid/ack_in             : cumulative ACK ("next expected" seq); out-of-window ignored
//   rewind                       : Go-Back-N: rd_seq := ack_seq (after this cycle's ACK)
//   ack_progress                 : pulse, ack_seq moved forward this cycle
//   rewind_moved                 : pulse, a rewind actually moved rd_seq (a replay starts)
//   ack_ignored                  : pulse, an out-of-window ACK was discarded
//   unacked                      : at least one flit awaits acknowledgement
module replay_buffer #(
    parameter integer DEPTH = 16,  // power of 2, < 128
    parameter integer BW    = 80
) (
    input  logic          clk,
    input  logic          rst_n,
    input  logic          enq_valid,
    input  logic [BW-1:0] enq_body,
    output logic          enq_ready,
    output logic          rd_valid,
    output logic [BW-1:0] rd_body,
    output logic [7:0]    rd_seq,
    input  logic          rd_advance,
    input  logic          ack_valid,
    input  logic [7:0]    ack_in,
    input  logic          rewind,
    output logic [7:0]    wr_seq,
    output logic [7:0]    ack_seq,
    output logic          ack_progress,
    output logic          rewind_moved,
    output logic          ack_ignored,
    output logic          unacked
);
  localparam integer IW = $clog2(DEPTH);
  localparam logic [7:0] DEPTH8 = DEPTH[7:0];

  // [0:N-1] kept for Yosys 0.33 compatibility
  // verilog_lint: waive unpacked-dimensions-range-ordering
  logic [BW-1:0] mem[0:DEPTH-1];
  logic [7:0] wr_q, rd_q, ack_q;
  logic [7:0] outstanding, ack_dist, ack_next, rd_adv, rd_floor, rd_next;
  logic       ack_ok, do_enq, do_adv;

  assign outstanding = wr_q - ack_q;
  assign enq_ready   = (outstanding < DEPTH8);
  assign do_enq      = enq_valid && enq_ready;
  assign rd_valid    = (rd_q != wr_q);
  assign do_adv      = rd_advance && rd_valid;
  assign rd_body     = mem[rd_q[IW-1:0]];

  // ACK is accepted only if it lies inside [ack_q, wr_q]
  assign ack_dist     = ack_in - ack_q;
  assign ack_ok       = ack_valid && (ack_dist <= outstanding);
  assign ack_next     = ack_ok ? ack_in : ack_q;
  assign ack_progress = ack_ok && (ack_in != ack_q);
  assign ack_ignored  = ack_valid && !ack_ok;

  // keep rd >= ack (a late ACK may overtake a timed-out rewind)
  assign rd_adv   = rd_q + {7'd0, do_adv};
  assign rd_floor = ((ack_next - ack_q) > (rd_adv - ack_q)) ? ack_next : rd_adv;
  assign rd_next  = rewind ? ack_next : rd_floor;
  assign rewind_moved = rewind && (rd_floor != ack_next);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      wr_q  <= 8'd0;
      rd_q  <= 8'd0;
      ack_q <= 8'd0;
    end else begin
      wr_q  <= wr_q + {7'd0, do_enq};
      rd_q  <= rd_next;
      ack_q <= ack_next;
    end
  end

  always_ff @(posedge clk) begin
    if (do_enq) mem[wr_q[IW-1:0]] <= enq_body;
  end

  assign wr_seq  = wr_q;
  assign rd_seq  = rd_q;
  assign ack_seq = ack_q;
  assign unacked = (wr_q != ack_q);

`ifdef D2D_CHECKS
  always_ff @(posedge clk) begin
    if (rst_n) begin
      assert (outstanding <= DEPTH8);
      assert ((rd_q - ack_q) <= outstanding);
    end
  end
`endif
endmodule
