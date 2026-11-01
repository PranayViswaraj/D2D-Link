`include "d2d_checks.svh"
// link_training_fsm - RESET -> TRAIN -> ACTIVE -> RETRAIN -> FAILED state machine.
// See docs/spec.md section 4.4 for the transition table.
// Ports:
//   enable, force_retrain           : CSR control (force_retrain is a 1-cycle pulse)
//   err_thresh, max_retrain,
//   err_window                      : CSR thresholds
//   flit_done, bad, train_good,
//   train_locked, nontrain_good     : receive events from flit_rx
//   state                           : current state (ST_* encoding)
//   locked                          : TRAIN_GOOD consecutive good TRAIN flits received
//   enter_active                    : pulse on TRAIN/RETRAIN -> ACTIVE (transmitter rewinds)
//   retrain_pulse                   : pulse on ACTIVE -> RETRAIN
module link_training_fsm #(
    parameter integer TRAIN_GOOD    = 8,
    parameter integer TRAIN_TIMEOUT = 1024,
    parameter integer STABLE_CYCLES = 2048
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,
    input  logic        force_retrain,
    input  logic [7:0]  err_thresh,
    input  logic [3:0]  max_retrain,
    input  logic [15:0] err_window,
    input  logic        flit_done,
    input  logic        bad,
    input  logic        train_good,
    input  logic        train_locked,
    input  logic        nontrain_good,
    output logic [2:0]  state,
    output logic        locked,
    output logic        enter_active,
    output logic        retrain_pulse
);
  `include "d2d_defs.svh"

  localparam integer GW = $clog2(TRAIN_GOOD + 1);
  localparam integer TW = $clog2(TRAIN_TIMEOUT + 1);
  localparam integer SW = $clog2(STABLE_CYCLES + 1);
  localparam logic [GW-1:0] GOOD_N  = TRAIN_GOOD[GW-1:0];
  localparam logic [TW-1:0] TMO_N   = TRAIN_TIMEOUT[TW-1:0];
  localparam logic [SW-1:0] STBL_N  = STABLE_CYCLES[SW-1:0];

  logic [2:0]    state_q, state_d;
  logic [GW-1:0] good_cnt;
  logic [TW-1:0] train_tmr;
  logic [SW-1:0] stable_tmr;
  logic [3:0]    attempts;
  logic [15:0]   win_cnt;
  logic [8:0]    win_err;
  logic          remote_ready, training, timeout, err_trip, retrain_req;

  assign training    = (state_q == ST_TRAIN) || (state_q == ST_RETRAIN);
  assign locked      = (good_cnt == GOOD_N);
  assign timeout     = training && (train_tmr == TMO_N);
  assign err_trip    = flit_done && bad && ((win_err + 9'd1) > {1'b0, err_thresh});
  // a peer TRAIN flit with LOCKED=1 means the peer is just finishing training: ignore it
  assign retrain_req = force_retrain || err_trip || (train_good && !train_locked);

  always_comb begin
    state_d = state_q;
    if (!enable) begin
      state_d = ST_RESET;
    end else begin
      case (state_q)
        ST_RESET: state_d = ST_TRAIN;
        ST_TRAIN, ST_RETRAIN: begin
          if (locked && remote_ready) state_d = ST_ACTIVE;
          else if (timeout && (attempts >= max_retrain)) state_d = ST_FAILED;
        end
        ST_ACTIVE: begin
          if (retrain_req) state_d = (attempts >= max_retrain) ? ST_FAILED : ST_RETRAIN;
        end
        ST_FAILED: state_d = ST_FAILED;
        default:   state_d = ST_RESET;
      endcase
    end
  end

  assign enter_active  = training && (state_d == ST_ACTIVE);
  assign retrain_pulse = (state_q == ST_ACTIVE) && (state_d == ST_RETRAIN);

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      state_q      <= ST_RESET;
      good_cnt     <= '0;
      train_tmr    <= '0;
      stable_tmr   <= '0;
      attempts     <= 4'd0;
      remote_ready <= 1'b0;
      win_cnt      <= 16'd0;
      win_err      <= 9'd0;
    end else begin
      state_q <= state_d;

      // ---- lock / handshake / training timer (TRAIN, RETRAIN) ----
      if (state_d != state_q || timeout) begin
        good_cnt     <= '0;
        remote_ready <= 1'b0;
        train_tmr    <= '0;
      end else if (training) begin
        train_tmr <= train_tmr + 1'b1;
        if (bad) good_cnt <= '0;
        else if (train_good && !locked) good_cnt <= good_cnt + 1'b1;
        if ((train_good && train_locked) || nontrain_good) remote_ready <= 1'b1;
      end

      // ---- retry attempt accounting ----
      if (state_d == ST_RESET) attempts <= 4'd0;
      else if (retrain_pulse || (timeout && state_d != ST_FAILED)) attempts <= attempts + 4'd1;
      else if (state_q == ST_ACTIVE && stable_tmr == STBL_N) attempts <= 4'd0;

      if (state_q != ST_ACTIVE || state_d != ST_ACTIVE) stable_tmr <= '0;
      else if (stable_tmr != STBL_N) stable_tmr <= stable_tmr + 1'b1;

      // ---- error window (ACTIVE only) ----
      if (state_q != ST_ACTIVE || state_d != ST_ACTIVE) begin
        win_cnt <= 16'd0;
        win_err <= 9'd0;
      end else if (flit_done) begin
        if (win_cnt + 16'd1 >= err_window) begin
          win_cnt <= 16'd0;
          win_err <= 9'd0;
        end else begin
          win_cnt <= win_cnt + 16'd1;
          if (bad) win_err <= win_err + 9'd1;
        end
      end
    end
  end

  assign state = state_q;

`ifdef D2D_CHECKS
  always_ff @(posedge clk) begin
    if (rst_n) begin
      assert (state_q <= ST_FAILED);
      assert (!(state_q == ST_FAILED && state_d != ST_FAILED && enable));
    end
  end
`endif
`ifdef FORMAL
  // FAILED is entered only once the retry budget is exhausted
  always_comb begin
    if (rst_n && state_q != ST_FAILED && state_d == ST_FAILED) assert (attempts >= max_retrain);
  end
`endif
endmodule
