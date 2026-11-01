// verilator lint_off UNUSEDPARAM
// d2d_defs.svh - shared constants for D2D-Link (included inside module bodies).
// Flit layout (see docs/spec.md section 3):
//   [127:124] TYPE  [123:116] SEQ  [115:108] ACK_SEQ  [107:100] CRED_REQ_CUM
//   [99:92] CRED_RSP_CUM  [91:88] FLAGS  [87:16] PAYLOAD  [15:0] CRC
// Flit body (FIFOs / replay buffer): {TYPE[3:0], FLAGS[3:0], PAYLOAD[71:0]} = 80 bits

localparam logic [3:0] FT_IDLE     = 4'd0;
localparam logic [3:0] FT_REQ_HDR  = 4'd1;
localparam logic [3:0] FT_REQ_DATA = 4'd2;
localparam logic [3:0] FT_RSP_HDR  = 4'd3;
localparam logic [3:0] FT_RSP_DATA = 4'd4;
localparam logic [3:0] FT_ACK      = 4'd5;
localparam logic [3:0] FT_NAK      = 4'd6;
localparam logic [3:0] FT_CREDIT   = 4'd7;
localparam logic [3:0] FT_TRAIN    = 4'd8;

localparam logic [71:0] TRAIN_PATTERN = 72'hD2D2_A5A5_5A5A_C3C3_3C;

// Link training states (CSR STATUS.LINK_STATE encoding)
localparam logic [2:0] ST_RESET   = 3'd0;
localparam logic [2:0] ST_TRAIN   = 3'd1;
localparam logic [2:0] ST_ACTIVE  = 3'd2;
localparam logic [2:0] ST_RETRAIN = 3'd3;
localparam logic [2:0] ST_FAILED  = 3'd4;
// verilator lint_on UNUSEDPARAM
