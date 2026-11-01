# Results

Every number below is copied from a log file in this repository; the source is given for
each table. Re-generate with `make regress formal syn report`.

## 1. Simulation regression
Source: `logs/regress/summary.md`, `logs/regress/junit.xml`, `logs/results_numbers.json`

| Metric | Value |
|--------|-------|
| Jobs (tests x seeds x configs) | 44 = (14 default-config tests + 8 small-config tests) x 2 seeds |
| Passed / failed | **44 / 0** |
| Regression base seed | 517299 (per-job seeds in `summary.md`) |
| Wall clock | 10.0 min on 4 parallel jobs (cap 15 min) |
| AXI transactions checked end to end | 5108 |
| Faulted flits injected (bit flips, multi-bit, beat, burst, drops) | 3604 |
| Bad flits detected (CRC/framing, both dies) | 1361 |
| NAKs sent | 350 |
| Go-Back-N replays | 353 |
| Replay timeouts | 62 |
| Retrains | 26 |
| Transactions lost / duplicated / corrupted | 0 (scoreboard: exact in-order expected stream + Die B request-stream check) |

A detected-bad-flit count lower than the injected count is expected: drops remove whole flits
(no CRC event; recovered by SEQ gap or timeout), and errors injected while a link is retraining
or failed are counted only as CRC errors.

## 2. Functional coverage
Source: `docs/coverage_report.md` (generated from `logs/regress/*/cov/*.json`)

**233 / 233 bins = 100.0%** across AXI (kind x ID, len x ID group, WSTRB classes, outstanding
depth), credit stalls per VC, replay depth, recovery type (NAK / timeout / retrain), every
training state and 11 transition arcs, CSR register x access type, fault type x VC and clock
ratio classes. An earlier full regression left writes to the read-only CSRs and four FSM
arcs (TRAIN->FAILED, ACTIVE->FAILED, TRAIN->RESET, RETRAIN->RESET) uncovered. They were closed
with the directed `ltssm_arcs` test and RO-write checks in `csr_access`, which also added real
checks: RO registers must ignore writes, and each arc is asserted, not just sampled.

## 3. Unit tests
Source: `logs/unit_final.log`, `logs/unit_junit.xml`

| Test file | Tests | Result |
|-----------|-------|--------|
| `tb/unit/test_common.py` | crc16 vs Python model (1004 vectors), async_fifo depth 4 and 16 (random unrelated clocks, fast-write/slow-read, slow-write/fast-read), credit_counter (all levels 0..MAX), reset_sync/sync_2ff latency | pass |
| `tb/unit/test_link_blocks.py` | replay_buffer vs Go-Back-N Python model (depth 4 and 16), flit_tx -> flit_rx loopback (TRAIN/ACK/IDLE/NAK, accept/duplicate/gap/CRC paths), training FSM directed | pass |
| **Total** | **9 pytest cases** | **9 passed** (667 s wall, run concurrently with formal) |

## 4. Formal (SymbiYosys, small configuration)
Source: `logs/formal_summary.txt`, `formal/<job>_<task>/logfile.txt`

| Job | Task | Engine | Result | Wall |
|-----|------|--------|--------|------|
| fifo (async FIFO, two unrelated clocks) | prove | ABC PDR (unbounded) | **PASS** | 240 s (job) |
| fifo | cover | smtbmc z3 | PASS (full, full+pop reachable) | |
| credit (cumulative credit protocol) | prove | ABC PDR (unbounded) | **PASS** | 17 s (job) |
| credit | cover | smtbmc z3 | PASS (credits 0 with buffer full) | |
| replay (replay-buffer pointers) | prove | k-induction (smtbmc z3) | **PASS** | 54 s (job) |
| replay | cover | smtbmc z3 | PASS (full buffer + replay) | |
| retry (reduced Go-Back-N link, lossy channel) | prove | ABC PDR (unbounded) | **PASS** | 121 s (job) |
| retry | cover | smtbmc z3 | PASS (replay happens, stream continues past it) | |
| ltssm (training FSM) | bmc | smtbmc z3, depth 20 | **PASS** (bounded) | 268 s (job) |
| ltssm | cover | smtbmc z3 | PASS (ACTIVE, RETRAIN->ACTIVE, FAILED reachable) | |

5 jobs / 10 tasks, all PASS: 4 unbounded proofs, 1 bounded (BMC depth 20) and 5 cover tasks.
Total formal wall clock: 709 s, run concurrently with the unit tests. That is over the 10-min
target; each task is within the 5-min cap.
Properties and assumptions are listed in `docs/verification_plan.md` section 6. Two
counterexamples found during bring-up were formal-setup errors (a clock-edge assertion vs a
combinational assumption in multiclock mode, and a wrapper check that used pre-reset history),
not RTL bugs; both are described in the git history of `formal/`.

## 5. Lint
Source: `logs/lint_verilator.log`, `logs/lint_verible.log`

| Tool | Result |
|------|--------|
| Verilator 5.020 `--lint-only -Wall`, synthesis view and `-DSIM` view | 0 warnings |
| Verible v0.0-4298 lint (`.rules.verible_lint`) | 0 violations |
| Waivers | 7, each justified in `docs/lint_waivers.md` |

## 6. Synthesis (ESTIMATES)
Source: `syn/reports/summary.txt`, `syn/reports/<block>.log`; script `scripts/run_syn.sh`
(wall clock 523 s, `logs/syn_run.log`). Yosys 0.33 `synth -flatten`, then `dfflibmap` + `abc`
with SKY130 HD `tt_025C_1v80`. **Area is standard-cell area only (no routing, no
utilization factor). Delay is ABC's `stime` longest combinational path with no wire load,
no clock tree, no clock-to-q/setup and no placement: treat it as a rough estimate, not
timing sign-off. OpenSTA is not installed.** No latches were inferred (`select -assert-none t:$dlatch`).

| Block (default params) | Generic cells | SKY130 area (um^2) | Flops | ABC comb. delay (ps) |
|---|---|---|---|---|
| async_fifo (80b x 16) | 2631 | 52,577 | 1320 | 14,781 |
| crc16 (112-bit, combinational) | 325 | 7,535 | 0 | 9,025 |
| replay_buffer (16 x 80b) | 2935 | 50,064 | 1304 | 11,038 |
| flit_tx | 1027 | 13,319 | 155 | 11,163 |
| flit_rx | 791 | 17,402 | 238 | 10,746 |
| link_training_fsm | 450 | 3,762 | 60 | 2,698 |
| link_layer | 7188 | 89,296 | 1894 | 20,827 |
| axi_slave_adapter | 242 | 1,695 | 12 | 3,378 |
| axi_master_adapter | 200 | 2,566 | 55 | 3,072 |
| apb_csr | 580 | 5,672 | 120 | 4,617 |
| **die_a_top** | 12126 | **179,397** | 4309 | 20,373 |
| **die_b_top** | 12499 | **175,826** | 4254 | 20,078 |

**Estimated fmax:** the worst combinational path is about 20.8 ns (`link_layer`), which bounds
clk_link at roughly **48 MHz in SKY130 tt** before register overheads. The path runs through
the replay-buffer read mux, header assembly and the 112-bit parallel CRC (the CRC alone is
about 9.0 ns), or on the receive side through the CRC check into the sequence/accept logic.
Known remedies (not implemented): register the CRC check (one extra receive pipeline stage),
compute the CRC per 32-bit beat, and replace the flop-based 16 x 80 replay and FIFO arrays
(about 2,600 of the ~4,300 flops per die) with SRAM or latch arrays.

## 7. SystemVerilog UVM (EDA Playground)
`uvm_sv/` contains a SystemVerilog UVM AXI master agent (item, sequence, driver, monitor,
agent, scoreboard, env, smoke test). It was syntax-checked locally with Verible
(`logs/verible_uvm_sv.log`: OK). It is intended to run on EDA Playground with UVM 1.2 and has
**not** been simulated locally (no SystemVerilog UVM simulator is available in this flow).

## 8. Tool runtimes (from logs)
| Step | Wall clock | Source |
|------|------------|--------|
| Full regression (44 jobs) | 10.0 min | `logs/regress/summary.md` |
| Formal (all jobs) | 709 s (5 jobs, 10 tasks) | `logs/formal_summary.txt` |
| Synthesis (12 blocks) | 523 s | `logs/syn_run.log` |
| Unit tests | 667 s (9 cases) | `logs/unit_final.log` |
