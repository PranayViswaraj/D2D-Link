`include "d2d_checks.svh"
// apb_csr - APB3 control/status registers for one die (clk_axi domain).
// Register map: docs/spec.md section 7. Writes to CTRL / ERR_CFG / ERR_WINDOW push a
// config message into the cfg async FIFO (pready is held low while it is full).
// Status snapshots from the link domain are popped from the sts async FIFO into
// shadow registers; interrupt events are detected by comparing snapshots.
// Ports:
//   psel..pslverr                 : APB3 slave (8-bit byte address)
//   irq                           : |(IRQ_STATUS & IRQ_EN)
//   cfg_full/cfg_wr_en/cfg_wdata  : config FIFO write side
//   sts_empty/sts_rdata/sts_rd_en : status FIFO read side
module apb_csr (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        psel,
    input  logic        penable,
    input  logic        pwrite,
    input  logic [7:0]  paddr,
    input  logic [31:0] pwdata,
    output logic [31:0] prdata,
    output logic        pready,
    output logic        pslverr,
    output logic        irq,
    input  logic        cfg_full,
    output logic        cfg_wr_en,
    output logic [29:0] cfg_wdata,
    input  logic        sts_empty,
    input  logic [82:0] sts_rdata,
    output logic        sts_rd_en
);
  `include "d2d_defs.svh"

  localparam logic [7:0] A_CTRL = 8'h00, A_STATUS = 8'h04, A_CRC = 8'h08, A_NAK = 8'h0C,
                         A_REPLAY = 8'h10, A_TMO = 8'h14, A_RETRAIN = 8'h18, A_ERRCFG = 8'h1C,
                         A_ERRWIN = 8'h20, A_IRQEN = 8'h24, A_IRQST = 8'h28, A_ID = 8'h2C;
  localparam logic [31:0] ID_VALUE = 32'hD2D1_0001;

  logic        ctrl_en;
  logic [7:0]  err_thresh;
  logic [3:0]  max_retrain;
  logic [15:0] err_window;
  logic [3:0]  irq_en, irq_st, irq_set;
  logic [2:0]  sh_state;
  logic [15:0] sh_crc, sh_nak, sh_replay, sh_tmo, sh_retrain;

  logic access, wr, rd, mapped, cfg_reg, stall;

  assign access  = psel && penable;
  assign cfg_reg = (paddr == A_CTRL) || (paddr == A_ERRCFG) || (paddr == A_ERRWIN);
  assign stall   = pwrite && cfg_reg && cfg_full;
  assign pready  = !stall;
  assign wr      = access && pwrite && !stall;
  assign rd      = access && !pwrite;

  always_comb begin
    mapped = 1'b1;
    prdata = 32'd0;
    case (paddr)
      A_CTRL:    prdata = {31'd0, ctrl_en};
      A_STATUS:  prdata = {28'd0, (sh_state == ST_ACTIVE), sh_state};
      A_CRC:     prdata = {16'd0, sh_crc};
      A_NAK:     prdata = {16'd0, sh_nak};
      A_REPLAY:  prdata = {16'd0, sh_replay};
      A_TMO:     prdata = {16'd0, sh_tmo};
      A_RETRAIN: prdata = {16'd0, sh_retrain};
      A_ERRCFG:  prdata = {20'd0, max_retrain, err_thresh};
      A_ERRWIN:  prdata = {16'd0, err_window};
      A_IRQEN:   prdata = {28'd0, irq_en};
      A_IRQST:   prdata = {28'd0, irq_st};
      A_ID:      prdata = ID_VALUE;
      default:   mapped = 1'b0;
    endcase
    if (!rd) prdata = 32'd0;
  end
  assign pslverr = access && !stall && !mapped;

  // ---------------- config registers + message ----------------
  logic        n_en, n_force;
  logic [7:0]  n_thresh;
  logic [3:0]  n_maxr;
  logic [15:0] n_win;

  always_comb begin
    n_en     = ctrl_en;
    n_force  = 1'b0;
    n_thresh = err_thresh;
    n_maxr   = max_retrain;
    n_win    = err_window;
    if (wr && paddr == A_CTRL) begin
      n_en    = pwdata[0];
      n_force = pwdata[1];
    end
    if (wr && paddr == A_ERRCFG) begin
      n_thresh = pwdata[7:0];
      n_maxr   = pwdata[11:8];
    end
    if (wr && paddr == A_ERRWIN) n_win = pwdata[15:0];
  end

  assign cfg_wr_en = wr && cfg_reg;
  assign cfg_wdata = {n_en, n_force, n_thresh, n_maxr, n_win};

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      ctrl_en     <= 1'b1;
      err_thresh  <= 8'd8;
      max_retrain <= 4'd4;
      err_window  <= 16'd256;
      irq_en      <= 4'd0;
    end else begin
      ctrl_en     <= n_en;
      err_thresh  <= n_thresh;
      max_retrain <= n_maxr;
      err_window  <= n_win;
      if (wr && paddr == A_IRQEN) irq_en <= pwdata[3:0];
    end
  end

  // ---------------- status snapshot + interrupts ----------------
  logic [2:0]  s_state;
  logic [15:0] s_crc, s_retrain;

  assign sts_rd_en = !sts_empty;
  assign s_state   = sts_rdata[82:80];
  assign s_crc     = sts_rdata[79:64];
  assign s_retrain = sts_rdata[15:0];

  always_comb begin
    irq_set = 4'd0;
    if (sts_rd_en) begin
      irq_set[0] = (sh_state == ST_ACTIVE) && (s_state != ST_ACTIVE);
      irq_set[1] = (s_retrain != sh_retrain);
      irq_set[2] = (s_state == ST_FAILED) && (sh_state != ST_FAILED);
      irq_set[3] = (s_crc != sh_crc);
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      sh_state   <= ST_RESET;
      sh_crc     <= 16'd0;
      sh_nak     <= 16'd0;
      sh_replay  <= 16'd0;
      sh_tmo     <= 16'd0;
      sh_retrain <= 16'd0;
      irq_st     <= 4'd0;
    end else begin
      if (sts_rd_en) begin
        sh_state   <= s_state;
        sh_crc     <= s_crc;
        sh_nak     <= sts_rdata[63:48];
        sh_replay  <= sts_rdata[47:32];
        sh_tmo     <= sts_rdata[31:16];
        sh_retrain <= s_retrain;
      end
      // set has priority over W1C clear
      irq_st <= ((wr && paddr == A_IRQST) ? (irq_st & ~pwdata[3:0]) : irq_st) | irq_set;
    end
  end

  assign irq = |(irq_st & irq_en);


  // Lint waiver (docs/lint_waivers.md): registers are at most 16 bits wide
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_ok;
  assign unused_ok = ^{pwdata[31:16]};
  /* verilator lint_on UNUSEDSIGNAL */

`ifdef D2D_CHECKS
  always_ff @(posedge clk) if (rst_n) assert (!(cfg_wr_en && cfg_full));
`endif
endmodule
