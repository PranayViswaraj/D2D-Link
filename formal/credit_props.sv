// credit_props - credit protocol model: transmitter credit_counter (MAX=4) + receiver
// buffer + lossy, delayed delivery of the CUMULATIVE freed count (as in link_layer).
// Proves credits stay in [0, MAX], the receiver buffer never overflows, and credits
// are conserved: count + buffer occupancy + not-yet-returned frees == MAX.
module credit_props (
    input logic       clk,
    input logic       rst_n,
    input logic       want_send,   // free: transmitter wants to send
    input logic       pop,         // free: receiver consumer frees one slot
    input logic       ack_vld,     // free: a good flit carrying the freed count arrives
    input logic [7:0] seen_cand    // free: which (stale) freed count it carries
);
  localparam integer MAX = 4;
  logic [2:0] count;
  logic       avail, consume;
  logic [7:0] ret, freed_cum, last_seen;
  logic [3:0] occ;

  assign consume = want_send && avail;

  credit_counter #(.MAX(MAX)) dut (
      .clk(clk), .rst_n(rst_n), .consume(consume), .ret(ret), .count(count), .avail(avail)
  );

  // receiver: flit lands in buffer, consumer pops, cumulative freed counter
  always_ff @(posedge clk) begin
    if (!rst_n) begin
      occ       <= 4'd0;
      freed_cum <= 8'd0;
      last_seen <= 8'd0;
    end else begin
      occ       <= occ + {3'd0, consume} - {3'd0, (pop && occ != 0)};
      freed_cum <= freed_cum + {7'd0, (pop && occ != 0)};
      if (ack_vld) last_seen <= seen_cand;
    end
  end
  // the carried value is some value the receiver had at an earlier time (monotone, <= current)
  always_comb assume ((seen_cand - last_seen) <= (freed_cum - last_seen));
  assign ret = ack_vld ? (seen_cand - last_seen) : 8'd0;

  logic init = 1'b1;
  always_ff @(posedge clk) init <= 1'b0;
  always_comb if (init) assume (!rst_n);

  always_comb begin
    if (!init && rst_n) begin
      assert (count <= MAX);
      assert (occ <= MAX);
      assert ({5'd0, count} + {4'd0, occ} + (freed_cum - last_seen) == 8'(MAX));
      cover (count == 0 && occ == MAX);
    end
  end
endmodule
