# Verification Plan

## 1. Strategy
| Level | Tool | Purpose |
|-------|------|---------|
| Unit | cocotb + Verilator | Each block against a Python model before integration |
| System | pyuvm + cocotb-coverage + Verilator | Constrained-random end-to-end on `d2d_system_top` with fault injection |
| Formal | SymbiYosys (BMC, small config) | Safety invariants of FIFO, credits, replay pointers, FSM, and a reduced retry model |
| SV-UVM | SystemVerilog UVM on EDA Playground | Demonstrates a classic SV UVM AXI agent against `die_a_top` (not run locally) |
| Static | Verilator `-Wall`, Verible lint, Yosys synth | Lint cleanliness, synthesizability, no latches |

Every test takes a seed (`SEED` env var, or a random one that gets logged). The regression
runs each system test over several seeds in parallel and writes JUnit XML.

## 2. System testbench architecture (pyuvm)

```
d2d_test_base
 └─ d2d_env
     ├─ axi_master_agent (Die A)     sequencer / driver / monitor
     ├─ axi_slave_mem_agent (Die B)  reactive driver (memory + random READY/latency) / monitor
     ├─ apb_agent[A], apb_agent[B]   sequencer / driver
     ├─ lane_fault_agent[a2b], [b2a] driver (XOR/drop per beat, flit-aligned on sof) / monitor
     ├─ virtual_sequencer            handles to all sequencers
     ├─ d2d_scoreboard               reference memory, order, loss/duplication checks
     └─ d2d_coverage                 cocotb-coverage covergroups
```

**Scoreboard checks**
1. Reference memory model: writes are applied in Die A acceptance order (honoring WSTRB). Each
   Die A read response is compared beat by beat against the model. Exact, because execution
   is strictly ordered (spec §5.3).
2. Die B request stream: each request seen at the Die B AXI master must equal the next Die A
   request (addr, len, id, wdata, wstrb). This catches loss, duplication and reordering at
   the point where it happens.
3. Response ID/RESP/RLAST correctness, and the beat count per burst.
4. End of test: every accepted transaction completed, nothing still outstanding, no extra
   responses. Both links ACTIVE, unless the test intends otherwise.
5. Fault accounting: the number of faulted flits injected is logged next to the CSR counters
   (CRC_ERR, NAK, REPLAY, TIMEOUT, RETRAIN). The test checks recovery: every transaction
   completes. Counter consistency is checked where it is deterministic (e.g. CRC_ERR ≥ 1 when
   flips were injected and the link was ACTIVE).

## 3. Feature → test → coverage → assertion matrix

| Feature | Tests | Coverage items | Assertions / formal |
|---------|-------|----------------|---------------------|
| F1 AXI transport | smoke, random_rw | `cp_kind` (rd/wr) × `cp_id` | scoreboard checks 1–3 |
| F2 bursts / WSTRB | random_rw, max_burst | `cp_len` (1..16) × `cp_id`; `cp_wstrb` (full, zero, single-byte, sparse, other) | scoreboard check 1 |
| F3 outstanding | outstanding_stress | `cp_outstanding_wr/rd` (0..4) | SIM assert: outstanding ≤ 4 |
| F4 CRC | crc_error_retry, unit test_crc16 | `cp_err_type` (single, multi, beat, burst, drop) × `cp_vc` | unit: CRC vs Python for random vectors |
| F5 credits / VCs | credit_starvation, backpressure_random | `cp_credit_stall` (REQ stall, RSP stall) | formal: credit in [0,MAX]; SIM: RX FIFO never written when full |
| F6 Go-Back-N | crc_error_retry, flit_drop_timeout | `cp_recovery` (NAK, timeout); `cp_replay_depth` (1, 2-4, 5-8, 9-16) | formal: replay pointer invariants; reduced retry model: in order, no loss/duplication |
| F7 training | error_storm_retrain, link_fail_and_recover | `cp_ltssm_state` (5 states), `cp_ltssm_trans` (all legal arcs) | formal: state always legal; cover: RETRAIN reachable, ACTIVE reached |
| F8 CDC | clock_ratio_sweep, unit test_async_fifo | `cp_clk_ratio` bins | formal: FIFO no overflow/underflow, gray one-bit change |
| F9 CSR | csr_access | `cp_csr_access` (reg × read/write), `cp_irq` | scoreboard: reset values, RW, RO, W1C |
| Reset | reset_during_traffic | – | scoreboard flush + post-reset traffic check |
| F10 fault injection | all fault tests | `cp_err_type` | – |

## 4. Test list

| Test | Description | Pass criteria |
|------|-------------|---------------|
| smoke | Train, 1 write + 1 read-back | data match, link ACTIVE |
| random_rw | 200 random reads/writes, random len/ID/WSTRB/addr | scoreboard clean |
| max_burst | 16-beat bursts back to back | scoreboard clean |
| outstanding_stress | Keep 4 wr + 4 rd outstanding, slow Die B memory | outstanding reaches 4, clean |
| credit_starvation | Die A host stalls BREADY/RREADY for long periods → RSP credits exhausted | RSP stall covered, clean |
| backpressure_random | Random VALID gaps at the host and random READY at the memory, both sides | clean |
| crc_error_retry | Random single/multi-bit flips, about 2% of flits, both directions | NAK count > 0, replays > 0, clean |
| flit_drop_timeout | Drop whole flits (tail flits in particular) | TIMEOUT > 0, clean |
| error_storm_retrain | Burst of heavy corruption → RETRAIN, then clean | RETRAIN ≥ 1, traffic completes, no loss |
| link_fail_and_recover | Corrupt everything until FAILED, then ENABLE toggle via APB | state FAILED seen, IRQ, recovery, no loss |
| csr_access | Reset values, RW/RO/W1C, unmapped → PSLVERR, force retrain | all checks |
| clock_ratio_sweep | Several unrelated clock period triples | clean for every ratio |
| reset_during_traffic | Assert reset mid-burst, re-train, new traffic | post-reset traffic clean |

## 5. Coverage goals
Functional coverage target: 100% of the bins defined in §3. Any bins not hit are listed with
the reason in `coverage_report.md`. Code coverage (Verilator `--coverage`) is collected for
information only.

## 6. Formal goals (small config, BMC depth 20–30, ≤ 5 min each)
| Job | Properties |
|-----|------------|
| fifo | !(push && full) never changes state; occupancy ≤ DEPTH; `$countones(g ^ $past(g)) ≤ 1` for both gray pointers; empty ⇔ occupancy==0 in the read domain view |
| credit | 0 ≤ credits ≤ MAX under arbitrary consume/return, given the environment assumption that returns never exceed what was consumed |
| replay | ack ≤ rd ≤ wr; wr - ack ≤ DEPTH; no enqueue when full; NAK/timeout rewinds stay in window |
| retry | Reduced model: replay_buffer + seq-check receiver over a lossy channel (any flit may be dropped/corrupted). Delivered SEQ stream is exactly 0,1,2,… (in order, no loss, no duplication). Cover: replay happens |
| ltssm | State ∈ {0..4}; FAILED only via the attempt limit; cover RETRAIN→ACTIVE |
