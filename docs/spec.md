# D2D-Link Specification

Version 1.0 — UCIe-*inspired* (not UCIe-compliant) die-to-die link controller.

## 1. Overview

D2D-Link carries AXI4 transactions from a host on **Die A** to a memory on **Die B**
across a flit-based, CRC-protected, retried, credit-flow-controlled link.

```
 host --AXI4--> [Die A: AXI slave adapter | link layer] ==lanes==> [Die B: link layer | AXI master adapter] --AXI4--> memory
                     clk_axi_a      clk_link                         clk_link     clk_axi_b
```

### 1.1 Feature list

| ID   | Feature |
|------|---------|
| F1   | AXI4 slave on Die A, AXI4 master on Die B: AW/W/B/AR/R, 64-bit data, 32-bit address, 4-bit ID |
| F2   | INCR bursts, AxLEN 0..15 (1..16 beats), AxSIZE passed through (TB uses 3 = 8 bytes), full WSTRB |
| F3   | Up to 4 outstanding writes and 4 outstanding reads at the Die A slave port |
| F4   | 128-bit flits with CRC-16-CCITT, sent as 4 beats on a 32-bit lane bus |
| F5   | Two virtual channels (REQ, RSP) with independent credit counters |
| F6   | Go-Back-N retry: 8-bit sequence numbers, replay buffer of `REPLAY_DEPTH` (16) flits, NAK and replay timeout |
| F7   | Link training FSM: RESET → TRAIN → ACTIVE → RETRAIN → FAILED, no data loss across a retrain |
| F8   | Three asynchronous clock domains; every data/control crossing is a gray-code async FIFO |
| F9   | APB3 CSR block per die: control, status, error counters, thresholds, W1C interrupts |
| F10  | Fault-injection ports on the lane bus (in the system top only) for verification |

### 1.2 Clock and reset domains

| Domain | Clock | Reset input | Contents |
|--------|-------|-------------|----------|
| AXI-A  | `clk_axi_a` | `rst_axi_a_n` | Die A AXI slave adapter, Die A APB CSR |
| AXI-B  | `clk_axi_b` | `rst_axi_b_n` | Die B AXI master adapter, Die B APB CSR |
| LINK   | `clk_link`  | `rst_link_n`  | Both link layers (one per die), lane bus |

All three clocks are mutually asynchronous. Every reset input goes through a `reset_sync`
in its own domain (asynchronous assert, synchronous deassert through 2 flops). All other
flops use a **synchronous** active-low reset driven by the synchronized reset. The RTL has no
`initial` blocks. In the system tests all three reset inputs come from one power-on reset,
so both sides of every async FIFO reset together (see `cdc.md` §4).

## 2. Interfaces

### 2.1 Die A (`die_a_top`)

| Port group | Direction | Description |
|------------|-----------|-------------|
| `s_axi_*`  | slave  | AXI4 AW/W/B/AR/R, clk_axi_a |
| `apb_*`    | slave  | APB3 `psel penable pwrite paddr[7:0] pwdata[31:0] prdata pready pslverr`, clk_axi_a |
| `irq`      | out    | Level interrupt, clk_axi_a |
| `lane_tx_{data[31:0],valid,sof}` | out | Lane bus toward Die B, clk_link |
| `lane_rx_{data[31:0],valid,sof}` | in  | Lane bus from Die B, clk_link |

### 2.2 Die B (`die_b_top`)
Same as Die A, except that it has an AXI4 **master** port `m_axi_*` on clk_axi_b.

### 2.3 System top (`d2d_system_top`)
Connects Die A and Die B lanes through a `lane_fault_inj` stage per direction.
Verification-only inputs (tie to 0 in a real system), all on clk_link:

| Input | Effect on the lane |
|-------|--------------------|
| `fi_a2b_xor[31:0]`, `fi_b2a_xor[31:0]` | XORed into lane data this beat (bit flips, beat corruption, burst errors) |
| `fi_a2b_drop`, `fi_b2a_drop` | Forces `valid` and `sof` low this beat. Driving it for all 4 beats of a flit drops that flit |

### 2.4 Lane bus protocol
- One beat per `clk_link` cycle while `valid=1`. A flit is 4 beats, MSB first: beat 0 carries
  bits [127:96] and has `sof=1`.
- A transmitter in TRAIN/RETRAIN/ACTIVE sends flits back-to-back (IDLE/ACK/CREDIT flits fill
  gaps). In RESET and FAILED it drives `valid=0`.
- The receiver realigns on `sof`. A flit that is interrupted (a new `sof` or `valid=0` before
  beat 3) is discarded and counted as a CRC/framing error.

## 3. Flit format (128 bits)

| Bits    | Field        | Description |
|---------|--------------|-------------|
| 127:124 | TYPE         | See table 3.1 |
| 123:116 | SEQ          | Sequence number (sequenced types only, else 0) |
| 115:108 | ACK_SEQ      | Piggybacked cumulative ACK: the **next expected** SEQ for the reverse direction |
| 107:100 | CRED_REQ_CUM | Cumulative count (mod 256) of REQ-VC buffer entries freed by this side's receiver |
| 99:92   | CRED_RSP_CUM | Same, for the RSP VC |
| 91:88   | FLAGS        | bit 88 = LAST (data flits) / LOCKED (TRAIN); 91:89 reserved (0) |
| 87:16   | PAYLOAD      | 72 bits, see table 3.2 |
| 15:0    | CRC          | CRC-16-CCITT over bits [127:16] |

**CRC:** polynomial 0x1021, initial value 0xFFFF, no input/output reflection, no final XOR
(CRC-16/CCITT-FALSE), computed MSB first over the 112-bit header+payload.

### 3.1 Flit types

| Code | Type     | Sequenced / replayed | VC  | Purpose |
|------|----------|----------------------|-----|---------|
| 0    | IDLE     | no  | –   | Filler. Still carries ACK/credit fields |
| 1    | REQ_HDR  | yes | REQ | AW or AR |
| 2    | REQ_DATA | yes | REQ | W beat |
| 3    | RSP_HDR  | yes | RSP | B response |
| 4    | RSP_DATA | yes | RSP | R beat |
| 5    | ACK      | no  | –   | Filler sent when the ACK value changed since the last flit |
| 6    | NAK      | no  | –   | Request Go-Back-N replay starting at ACK_SEQ |
| 7    | CREDIT   | no  | –   | Filler sent when a credit count changed |
| 8    | TRAIN    | no  | –   | Training pattern. Payload must equal `TRAIN_PATTERN` |
| 9–15 | reserved | –   | –   | Treated as a corrupted flit |

ACK_SEQ and the credit fields are cumulative, so losing any single flit never loses an ACK
or a credit: the next good flit carries the up-to-date values. They are only consumed from
good-CRC, non-TRAIN flits while the receiver is ACTIVE.

### 3.2 Payload formats (bits relative to flit)

| Type     | Layout |
|----------|--------|
| REQ_HDR  | [87] is_write, [86:83] id, [82:51] addr, [50:47] len, [46:44] size, [43:42] burst, rest 0 |
| REQ_DATA | [87:24] wdata, [23:16] wstrb, FLAGS.LAST = wlast |
| RSP_HDR  | [87:84] bid, [83:82] bresp, rest 0 |
| RSP_DATA | [87:24] rdata, [23:20] rid, [19:18] rresp, FLAGS.LAST = rlast |
| TRAIN    | [87:16] = `72'hD2D_A5A5_5A5A_C3C3_3C` (TRAIN_PATTERN), FLAGS.LOCKED |

Inside a die, flits travel through the CDC FIFOs and the replay buffer as an 80-bit **flit
body** `{TYPE[3:0], FLAGS[3:0], PAYLOAD[71:0]}`. SEQ, ACK, credit fields and CRC are added
by `flit_tx` when the flit is serialized.

## 4. Link layer

### 4.1 Transmit path (`flit_tx` + `replay_buffer` + `credit_counter`)
1. **Enqueue.** Each cycle, at most one flit body moves from a TX VC FIFO into the replay
   buffer. That needs: the replay buffer not full, at least one credit for that VC, and the
   link not in RESET or FAILED. The two VCs are arbitrated round-robin. Enqueueing assigns
   SEQ = `wr_seq` and consumes one credit.
2. **Send.** At each flit boundary the transmitter picks, in priority order:
   (a) TRAIN while training, (b) NAK if one is pending, (c) the replay-buffer entry at `rd_seq`
   if `rd_seq != wr_seq`, (d) ACK if the ACK value changed, (e) CREDIT if a credit count
   changed, (f) IDLE.
3. **Retire.** A received ACK_SEQ `a` is valid when `(a - ack_seq) mod 256 <= (wr_seq - ack_seq) mod 256`.
   Entries below `a` are freed and `ack_seq := a`. An invalid ACK is ignored, and
   asserts in simulation.
4. **Replay.** On a valid NAK(a): retire up to `a`, then `rd_seq := a`. On replay timeout
   (`ack_seq != wr_seq` and no ACK progress for `REPLAY_TIMEOUT` link cycles): `rd_seq := ack_seq`.
   When the link re-enters ACTIVE from RETRAIN: `rd_seq := ack_seq`. Replay counter increments
   whenever a rewind actually moves `rd_seq`.

Invariant (formally proven): `ack_seq ≤ rd_seq ≤ wr_seq` and `wr_seq - ack_seq ≤ REPLAY_DEPTH`
(mod-256 distances). `REPLAY_DEPTH` (16) < 128 = half the sequence space, so the receiver can
tell a duplicate from a future flit without ambiguity.

### 4.2 Receive path (`flit_rx`)
- Deserialize 4 beats, check the CRC and that TYPE is legal.
- **Bad flit** (CRC, framing, reserved type, bad TRAIN pattern): increment the CRC error
  counter. In ACTIVE, if no NAK is outstanding, request a NAK with ACK_SEQ = `exp_seq` and set
  `nak_outstanding`.
- **Good sequenced flit** in ACTIVE:
  - `seq == exp_seq`: push the body into the RX VC FIFO, `exp_seq++`, clear `nak_outstanding`.
  - `(seq - exp_seq) mod 256 < 128` (a gap, so a flit was lost): request a NAK as above.
  - otherwise it is a duplicate: drop silently. The cumulative ACK re-acknowledges it.
- Good flits in ACTIVE also deliver ACK_SEQ, NAK and the credit fields to the local transmitter.
- If the NAK itself is lost, the far side's replay timeout recovers.

### 4.3 Credit flow control
- One credit = one flit-body slot in the far side's RX VC FIFO. Each RX VC FIFO is an async FIFO
  of depth `CREDITS_REQ` / `CREDITS_RSP`.
- The receiver's freed count is the RX FIFO read pointer as seen in the link domain (already
  gray-synchronized inside the FIFO), accumulated mod 256 into `CRED_*_CUM`.
- The transmitter keeps `sent_cum` per VC. Available credits =
  `CREDITS - (sent_cum - freed_cum) mod 256`, kept in `credit_counter` with consume and return-N
  ports. Formally proven to stay within [0, CREDITS].
- Credits are consumed at enqueue, not when a flit is sent, so a replay never consumes a credit
  again. A flit accepted in order therefore always has a free FIFO slot (asserted).
- REQ and RSP have independent credits. A full REQ path can never block responses, which removes
  the request/response protocol deadlock.

### 4.4 Link training FSM (`link_training_fsm`)

| State   | Code | Lane output | Description |
|---------|------|-------------|-------------|
| RESET   | 0 | idle (`valid=0`) | Waiting for `enable` |
| TRAIN   | 1 | TRAIN flits | Initial training |
| ACTIVE  | 2 | data/control flits | Normal operation |
| RETRAIN | 3 | TRAIN flits | Retraining. Sequence, replay and credit state are kept |
| FAILED  | 4 | idle | Too many failed attempts. Sticky until `enable` is cleared |

`locked` = `TRAIN_GOOD` (default 8, small 4) consecutive good TRAIN flits received since entering
the state. Any bad flit clears the count. Each TRAIN flit we send carries our `locked` bit.
`remote_ready` = a good TRAIN flit with LOCKED=1 was received, or any good non-TRAIN flit.

| From | Condition (priority order) | To | Actions |
|------|----------------------------|----|---------|
| any  | `!enable` | RESET | clear attempts |
| RESET | `enable` | TRAIN | |
| TRAIN / RETRAIN | `locked && remote_ready` | ACTIVE | rewind `rd_seq := ack_seq` |
| TRAIN / RETRAIN | training timer reaches `TRAIN_TIMEOUT` and `attempts == MAX_RETRAIN` | FAILED | |
| TRAIN / RETRAIN | training timer reaches `TRAIN_TIMEOUT` | same | `attempts++`, restart lock |
| ACTIVE | errors in current window > `err_thresh`, or `force_retrain`, or good TRAIN flit with LOCKED=0 | RETRAIN | `retrain_cnt++`, `attempts++` (FAILED instead if `attempts == MAX_RETRAIN`) |
| ACTIVE | `STABLE_CYCLES` in ACTIVE with no retrain | ACTIVE | clear attempts |

A TRAIN flit with LOCKED=1 received while ACTIVE is ignored: the peer is just finishing
training. Without that rule the two FSMs would livelock. The error window counts received
flits. After `err_window` flits the window error count is cleared.

**No loss across retrain:** the replay buffer, `exp_seq`, the credit counters and the RX FIFOs
are not touched by training. After returning to ACTIVE the transmitter replays everything
unacknowledged, and the receiver drops duplicates by SEQ.

## 5. AXI adapters and ordering

### 5.1 Die A slave adapter
- One request FSM serializes both channels into the REQ stream: either one AW followed by all
  of its W beats, or one AR. When both are pending it alternates between writes and reads
  (round-robin). AW and AR are never accepted in the same cycle, so the global request order
  is the handshake order.
- AW is accepted only if fewer than 4 writes are outstanding; AR only if fewer than 4 reads.
  A write retires on its B handshake, a read on its R handshake with RLAST.
- Responses come back in request order. The B and R channels are driven from the head of the
  RSP stream.

### 5.2 Die B master adapter
- Executes requests strictly one at a time in arrival order: AW, then W beats, then wait for B;
  or AR, then forward R beats until RLAST.
- RREADY/BREADY are asserted only when the RSP TX FIFO can accept the flit.

### 5.3 Ordering rules (restrictions)
- All transactions, reads and writes, are executed at Die B in Die A acceptance order, one at a
  time. Responses are returned in order. Different IDs are **not** reordered. Strict ordering is
  legal AXI behavior, at the cost of performance.
- Only INCR bursts are supported; FIXED/WRAP encodings are forwarded unchanged and are not verified.
- Requests must not cross a 4 KB boundary (AXI rule, assumed of the host).
- No error responses are generated by the link. Die B's BRESP/RRESP are forwarded unchanged.

## 6. Error handling summary

| Event | Detection | Recovery | Counter |
|-------|-----------|----------|---------|
| Bit flips / beat corruption | CRC | NAK → Go-Back-N replay | CRC_ERR, NAK, REPLAY |
| Dropped sequenced flit | SEQ gap at the next sequenced flit | NAK → replay | NAK, REPLAY |
| Dropped last flit / lost NAK / lost ACKs | Replay timeout | Replay from oldest unacked | TIMEOUT, REPLAY |
| Error burst above threshold | Window error counter | RETRAIN, then replay | RETRAIN |
| Repeated retrain failure | Attempt counter | FAILED, interrupt; software toggles CTRL.ENABLE | RETRAIN |
| Duplicate flit after replay | SEQ < expected | Dropped | – |

## 7. CSR map (APB3, per die, clk_axi domain)

All registers are 32-bit, addresses are byte offsets, and unused bits read 0. Access to an
unmapped address returns `pslverr=1`. `pready` is always 1 (no wait states).

| Offset | Name | Access | Reset | Fields |
|--------|------|--------|-------|--------|
| 0x00 | CTRL | RW | 0x1 | [0] ENABLE, [1] FORCE_RETRAIN (write 1 = pulse, reads 0) |
| 0x04 | STATUS | RO | 0x0 | [2:0] LINK_STATE (see 4.4), [3] LINK_UP (state==ACTIVE) |
| 0x08 | CRC_ERR_CNT | RO | 0 | [15:0] saturating |
| 0x0C | NAK_CNT | RO | 0 | [15:0] NAKs sent by this die's receiver |
| 0x10 | REPLAY_CNT | RO | 0 | [15:0] replays started by this die's transmitter |
| 0x14 | TIMEOUT_CNT | RO | 0 | [15:0] replay timeouts |
| 0x18 | RETRAIN_CNT | RO | 0 | [15:0] ACTIVE→RETRAIN transitions |
| 0x1C | ERR_CFG | RW | 0x0000_0408 | [7:0] ERR_THRESH, [11:8] MAX_RETRAIN |
| 0x20 | ERR_WINDOW | RW | 0x0000_0100 | [15:0] window length in received flits |
| 0x24 | IRQ_EN | RW | 0x0 | [0] LINK_DOWN, [1] RETRAIN, [2] LINK_FAILED, [3] CRC_ERR |
| 0x28 | IRQ_STATUS | W1C | 0x0 | same bits; set on event, cleared by writing 1 |
| 0x2C | ID | RO | 0xD2D1_0001 | constant |

`irq = |(IRQ_STATUS & IRQ_EN)`. Interrupt events are detected in the clk_axi domain by
comparing consecutive status snapshots:
- LINK_DOWN: state left ACTIVE.
- RETRAIN: RETRAIN_CNT changed.
- LINK_FAILED: state became FAILED.
- CRC_ERR: CRC_ERR_CNT changed.

**Counter synchronization:** counters live in the link domain. The link domain pushes a
complete status snapshot (state + 5 counters) into a dedicated async FIFO whenever it has
space. The CSR domain pops it and updates shadow registers. A software read therefore
returns one coherent, slightly delayed snapshot. A multi-bit counter never crosses through
individual synchronizers. Configuration (ENABLE, FORCE_RETRAIN pulse, thresholds) travels the
other way as a message in a second async FIFO, written on each CSR write. The link domain
resets to the same defaults as the CSRs.

## 8. Parameters

| Parameter | Default | Small | Notes |
|-----------|---------|-------|-------|
| DATA_W | 64 | 64 | Fixed by the flit payload layout |
| FLIT_W | 128 | 128 | Fixed by the header layout |
| REPLAY_DEPTH | 16 | 4 | Power of 2, < 128 |
| CREDITS_REQ | 16 | 4 | = REQ RX FIFO depth, power of 2 |
| CREDITS_RSP | 16 | 4 | = RSP RX FIFO depth, power of 2 |
| TX_FIFO_DEPTH | 8 | 4 | AXI→link CDC FIFOs |
| REPLAY_TIMEOUT | 256 | 128 | link cycles |
| TRAIN_GOOD | 8 | 4 | consecutive good TRAIN flits to lock |
| TRAIN_TIMEOUT | 1024 | 512 | link cycles per training attempt |
| STABLE_CYCLES | 2048 | 1024 | ACTIVE time that clears the attempt counter |

## 9. Known limitations
1. Strict in-order execution at Die B, one transaction at a time, so link utilization is low.
   There is no per-ID reordering.
2. One flit per AXI data beat: 80 useful bits out of 128 per flit, and 4 link cycles per beat.
3. Only INCR bursts are verified. No exclusive access, QoS, cache or prot handling (these
   signals are not carried).
4. Resets of the two dies are assumed simultaneous. An independent single-die reset in the
   middle of traffic is not supported.
5. FAILED needs software intervention (ENABLE 1→0→1). In-flight traffic is preserved across
   that, because sequence state survives an ENABLE toggle.
6. The lane model is an ideal parallel bus with a fault-injection XOR. There is no PHY,
   deskew, scrambling or lane repair.
7. Lane framing (`valid`/`sof`) is assumed trustworthy except for whole-beat drops.
