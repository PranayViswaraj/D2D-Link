# Bug Log

Real defects found during verification, with the test or assertion that caught each one.
Testbench-only mistakes are listed separately so the RTL record stays honest.

## RTL bugs

### #1 — AXI READY / APB PREADY asserted while the synchronized reset is still active
- **Symptom:** `reset_during_traffic` (seed 112) hung after the mid-traffic reset. The link
  was ACTIVE and idle, the REQ TX FIFO was empty, and the host held WVALID=1 with WREADY=0
  forever. The heartbeat log showed `wr_seq=0`: no flit had been sent since the reset.
- **Root cause:** the pin reset deasserts 2 `clk_axi_a` cycles before the internally
  synchronized reset (`reset_sync` deasserts through 2 flops). In that window
  `axi_slave_adapter` drove `s_axi_awready = !in_wdata && awvalid && ...`, built entirely from
  reset-state values, so it was 1. A host that started right after reset completed an AW
  handshake that the still-in-reset flops never captured. The adapter stayed out of the
  W-data state, so the W beats were never accepted: a lost transaction and a hung bus.
  `apb_csr.pready` had the same issue (a CSR write in that window would be dropped).
- **Fix:** gate `wr_ok`/`rd_ok` (`awready`/`arready`), `wready` and `pready` with the
  synchronized `rst_n` (`rtl/axi_slave_adapter.sv`, `rtl/apb_csr.sv`). Die B's master adapter
  was already safe: its READY outputs come from its reset state register.
- **Caught by:** `reset_during_traffic` (end-of-traffic check and drain), diagnosed with
  link-internal probes from the test heartbeat.
- **Lesson:** every handshake output that is a combinational function of state must be
  qualified by the domain's synchronized reset, not just its registers.

## Investigated, not a bug (design characterization)

### C1 — Link escalates to FAILED at a 3% per-flit error rate
- **Symptom:** `crc_error_retry` (default config, seeds 49065 and 50078) hung with both dies in
  FAILED after about 107 transactions; an earlier seed had passed.
- **Analysis:** the retrain threshold is more than 8 bad flits in a 256-flit window (about 3.1%).
  A uniform 3% flit error rate averages 7.7 errors per window, so windows regularly exceed the
  threshold. The retrains recur within `STABLE_CYCLES`, which exhausts `MAX_RETRAIN` (4), and
  the link goes FAILED, exactly as specified (spec 4.4).
- **Resolution:** no RTL change. `crc_error_retry` now injects 1% (below the threshold) so that
  it targets NAK/replay. Escalation stays covered by `error_storm_retrain` and
  `link_fail_and_recover`. The base test gained a fail-fast watchdog, so an unexpected FAILED
  link fails immediately instead of hanging until the timeout.
- **Takeaway:** the thresholds encode a BER budget. A real product would characterize the
  retrain threshold against the expected channel BER, and the CSRs make that tunable.

## Testbench bugs (not design defects)

| # | Symptom | Cause | Fix |
|---|---------|-------|-----|
| T1 | Duplicate AW risk found in review before the first run | BFMs sampled READY *after* the rising edge, when combinational READY may already reflect the new state | All BFMs drive on the falling edge and sample in ReadOnly before the rising edge |
| T2 | `flit_loopback` unit test: second flit not accepted | Test dropped `rb_valid` before the edge on which `flit_tx` loaded the flit | Sample `rb_advance` before the edge, release after it |
| T3 | `flit_drop_timeout` saw 0 replay timeouts (all drops recovered by NAK) | Dense traffic: every dropped flit was followed by a sequenced flit, so the SEQ gap triggered a NAK first | Added a sparse single-beat phase in which only the timeout can recover; the timeout assertion is unchanged |
| T4 | After a mid-burst reset the host driver kept offering W beats for an AW the DUT had forgotten | Driver only checked `rst_n` inside handshakes, not across idle gaps | Reset epoch counter: items started before a reset are abandoned |
| T5 | `reset_during_traffic` reported 100 requests / 98 responses | Transactions destroyed by the reset were still counted | Scoreboard counts transactions flushed by reset; invariant is `requests == responses + flushed` |
