# Clock-Domain Crossing Report

## 1. Domains
`clk_axi_a`, `clk_axi_b` and `clk_link` are mutually asynchronous. The verification sweeps
unrelated ratios between them (see `clock_ratio_sweep`).

## 2. Crossing inventory

Every multi-bit crossing is an `async_fifo` instance. Inside each FIFO, the only signals that
cross are gray-coded pointers, each through a `sync_2ff`. No other signal crosses a domain
boundary.

| # | Die | Instance | From → To | Width | Depth | Content |
|---|-----|----------|-----------|-------|-------|---------|
| 1 | A | `u_req_tx_fifo` | axi_a → link | 80 | TX_FIFO_DEPTH | REQ flit bodies (AW/AR headers, W beats) |
| 2 | A | `u_rsp_rx_fifo` | link → axi_a | 80 | CREDITS_RSP | RSP flit bodies (B, R beats) — is the RSP credit buffer |
| 3 | A | `u_cfg_fifo` | axi_a → link | 30 | 4 | Config message {enable, force_retrain, err_thresh, max_retrain, err_window} |
| 4 | A | `u_sts_fifo` | link → axi_a | 83 | 4 | Status snapshot {state, 5×16-bit counters} |
| 5 | B | `u_req_rx_fifo` | link → axi_b | 80 | CREDITS_REQ | REQ flit bodies — is the REQ credit buffer |
| 6 | B | `u_rsp_tx_fifo` | axi_b → link | 80 | TX_FIFO_DEPTH | RSP flit bodies |
| 7 | B | `u_cfg_fifo` | axi_b → link | 30 | 4 | Config message |
| 8 | B | `u_sts_fifo` | link → axi_b | 83 | 4 | Status snapshot |

Reset synchronizers (`reset_sync`, one per domain per die) are the only other synchronizers.
They carry a 1-bit reset with asynchronous assertion and synchronous deassertion.

## 3. Async FIFO design rules
- Binary and gray pointers are `AW+1` bits wide (one extra wrap bit). The gray pointer is
  **registered** before it crosses, so no combinational glitches reach the synchronizer.
- Full: `wgray_next == {~rgray_sync[AW:AW-1], rgray_sync[AW-2:0]}`. Empty: `rgray_next == wgray_sync`.
  Both flags are registered.
- Formally proven (small config): no write when full corrupts state, no read when empty, the
  gray pointers change at most one bit per clock, and the occupancy never exceeds `DEPTH`.
- The write domain also gets `wr_rcount` (the synchronized read pointer converted to binary).
  The link layer uses it for credit return (decision 2 in microarch). It is a pessimistic
  view: it lags the real read pointer by 2–3 write clocks, so credits come back late, never
  early.

## 4. Reset across the crossing
Both sides of a FIFO must reset together. Each die's domains reset from one reset input that
is synchronized separately into each domain, and the assertion is asynchronous. Assertion
therefore reaches both sides at once, and deassertion is staggered by at most the
synchronizer latency. While one side is still in reset its pointers are 0, which the other
side reads as "empty"/"not full". That is safe because no traffic is generated until the link
has trained (more than 1000 cycles). Independent per-die reset during traffic is a documented
limitation (spec §9).

## 5. Counter / status crossing
Counters are **not** gray-coded and never cross bit by bit. The link domain writes a whole
snapshot word into `u_sts_fifo` whenever the FIFO is not full. The CSR domain pops whenever it
is not empty and latches the snapshot into shadow registers. A software read is coherent
(all fields from the same link cycle) and at most a few clocks stale.

Config goes the other way. FORCE_RETRAIN is a 1-cycle pulse in the link domain, produced
when the message containing `force_retrain=1` is popped, so a pulse can never be lost or
duplicated, whatever the clock ratio.

## 6. Static checks performed
- `verilator --lint-only -Wall`: zero warnings (see `logs/lint_verilator.log`).
- Review checklist: every `always_ff` uses exactly one clock. Signals from the other domain
  appear only as `async_fifo` ports. The `sync_2ff` input is driven by a flop in the source
  domain.
- No open-source structural CDC checker is used. The checklist above is a manual review,
  aided by the per-domain module boundaries, since every module except `async_fifo` and the
  die tops has a single clock port.
