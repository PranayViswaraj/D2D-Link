// csr_link_sync - link-domain side of the CSR crossing.
// Pops configuration messages (written by apb_csr through an async FIFO) into
// registers, and continuously pushes a coherent status snapshot into the status
// async FIFO whenever it has space. Reset values match apb_csr reset values.
// Ports:
//   cfg_empty/cfg_rdata/cfg_rd_en  : config FIFO read side
//                                    msg = {enable, force_retrain, err_thresh[7:0], max_retrain[3:0], err_window[15:0]}
//   enable..err_window             : configuration outputs (force_retrain = 1-cycle pulse)
//   link_state, *_cnt              : status inputs from link_layer
//   sts_full/sts_wr_en/sts_wdata   : status FIFO write side
//                                    snapshot = {state[2:0], crc, nak, replay, timeout, retrain}
module csr_link_sync (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        cfg_empty,
    input  logic [29:0] cfg_rdata,
    output logic        cfg_rd_en,
    output logic        enable,
    output logic        force_retrain,
    output logic [7:0]  err_thresh,
    output logic [3:0]  max_retrain,
    output logic [15:0] err_window,
    input  logic [2:0]  link_state,
    input  logic [15:0] crc_err_cnt,
    input  logic [15:0] nak_cnt,
    input  logic [15:0] replay_cnt,
    input  logic [15:0] timeout_cnt,
    input  logic [15:0] retrain_cnt,
    input  logic        sts_full,
    output logic        sts_wr_en,
    output logic [82:0] sts_wdata
);
  assign cfg_rd_en = !cfg_empty;

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      enable        <= 1'b1;
      force_retrain <= 1'b0;
      err_thresh    <= 8'd8;
      max_retrain   <= 4'd4;
      err_window    <= 16'd256;
    end else begin
      force_retrain <= 1'b0;
      if (cfg_rd_en) begin
        enable        <= cfg_rdata[29];
        force_retrain <= cfg_rdata[28];
        err_thresh    <= cfg_rdata[27:20];
        max_retrain   <= cfg_rdata[19:16];
        err_window    <= cfg_rdata[15:0];
      end
    end
  end

  assign sts_wr_en = !sts_full;
  assign sts_wdata = {link_state, crc_err_cnt, nak_cnt, replay_cnt, timeout_cnt, retrain_cnt};
endmodule
