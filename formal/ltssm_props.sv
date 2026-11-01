// ltssm_props - link_training_fsm with unconstrained inputs (small timers).
// The embedded assertions (state legal, FAILED sticky while enabled) plus the checks
// below are proven; covers show TRAIN->ACTIVE, ACTIVE->RETRAIN->ACTIVE and FAILED.
module ltssm_props (
    input logic        clk,
    input logic        rst_n,
    input logic        enable,
    input logic        force_retrain,
    input logic [7:0]  err_thresh,
    input logic [3:0]  max_retrain,
    input logic [15:0] err_window,
    input logic        flit_done,
    input logic        bad,
    input logic        train_good,
    input logic        train_locked,
    input logic        nontrain_good
);
  logic [2:0] state;
  logic       locked, enter_active, retrain_pulse;

  link_training_fsm #(.TRAIN_GOOD(2), .TRAIN_TIMEOUT(8), .STABLE_CYCLES(8)) dut (
      .clk(clk), .rst_n(rst_n), .enable(enable), .force_retrain(force_retrain),
      .err_thresh(err_thresh), .max_retrain(max_retrain), .err_window(err_window),
      .flit_done(flit_done), .bad(bad), .train_good(train_good), .train_locked(train_locked),
      .nontrain_good(nontrain_good), .state(state), .locked(locked),
      .enter_active(enter_active), .retrain_pulse(retrain_pulse)
  );

  // receive events are mutually consistent (as produced by flit_rx)
  always_comb begin
    assume (!(train_good && (bad || nontrain_good)));
    assume (!(bad && nontrain_good));
    assume ((train_good || bad || nontrain_good) == flit_done);
    assume (max_retrain <= 4'd2);
  end

  logic init = 1'b1;
  logic [2:0] prev = 3'd0;
  logic seen_retrain = 1'b0;
  always_ff @(posedge clk) begin
    init <= 1'b0;
    prev <= state;
    if (state == 3'd3) seen_retrain <= 1'b1;
  end
  always_comb if (init) assume (!rst_n);

  always_comb begin
    if (!init && rst_n) begin
      assert (state <= 3'd4);
      // ACTIVE is only entered from TRAIN/RETRAIN, and only with a lock
      if (state == 3'd2 && prev != 3'd2) assert (prev == 3'd1 || prev == 3'd3);
      assert (!(enter_active && !locked));
      cover (state == 3'd2);
      cover (seen_retrain && state == 3'd2);
      cover (state == 3'd4);
    end
  end
endmodule
