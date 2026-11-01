// crc16 - combinational parallel CRC-16-CCITT (poly 0x1021, init 0xFFFF,
// no reflection, no final XOR = CRC-16/CCITT-FALSE), MSB first.
// Ports:
//   data : N-bit message, bit N-1 is processed first
//   crc  : resulting CRC
module crc16 #(
    parameter integer N = 112
) (
    input  logic [N-1:0] data,
    output logic [15:0]  crc
);
  always_comb begin : p_crc
    logic [15:0] c;
    logic        fb;
    c = 16'hFFFF;
    for (int i = N - 1; i >= 0; i--) begin
      fb = c[15] ^ data[i];
      c  = {c[14:0], 1'b0} ^ (fb ? 16'h1021 : 16'h0000);
    end
    crc = c;
  end
endmodule
