# D2D-Link Micro-architecture

## 1. System block diagram

```mermaid
flowchart LR
  subgraph DA["die_a_top"]
    direction LR
    AS["axi_slave_adapter<br/>clk_axi_a"]
    CSRA["apb_csr<br/>clk_axi_a"]
    FTXA[["async_fifo<br/>REQ TX"]]
    FRXA[["async_fifo<br/>RSP RX"]]
    CFGA[["async_fifo<br/>cfg"]]
    STA[["async_fifo<br/>status"]]
    LLA["link_layer<br/>clk_link"]
    AS --> FTXA --> LLA
    LLA --> FRXA --> AS
    CSRA --> CFGA --> LLA
    LLA --> STA --> CSRA
  end
  subgraph DB["die_b_top"]
    direction LR
    LLB["link_layer<br/>clk_link"]
    FRXB[["async_fifo<br/>REQ RX"]]
    FTXB[["async_fifo<br/>RSP TX"]]
    AM["axi_master_adapter<br/>clk_axi_b"]
    CSRB["apb_csr<br/>clk_axi_b"]
    LLB --> FRXB --> AM
    AM --> FTXB --> LLB
    CSRB <-->|cfg / status FIFOs| LLB
  end
  HOST((AXI host)) --> AS
  AM --> MEM((AXI memory))
  LLA -- "lane a2b (32b x 4 beats)" --> FIA{{lane_fault_inj}} --> LLB
  LLB -- "lane b2a" --> FIB{{lane_fault_inj}} --> LLA
```

## 2. Link layer internals

```mermaid
flowchart TB
  subgraph LL["link_layer (clk_link)"]
    ARB["VC round-robin enqueue<br/>(credit + space check)"]
    CCQ["credit_counter REQ"]
    CCS["credit_counter RSP"]
    RB["replay_buffer<br/>wr_seq / rd_seq / ack_seq"]
    TX["flit_tx<br/>select, header insert,<br/>crc16, 4-beat serializer"]
    RX["flit_rx<br/>deserialize, crc16 check,<br/>seq check, NAK gen"]
    FSM["link_training_fsm"]
    CNT["error counters +<br/>error window"]
    CRED["freed-credit accumulators<br/>(from RX FIFO rptr)"]
  end
  TXREQ[/tx_req FIFO/] --> ARB
  TXRSP[/tx_rsp FIFO/] --> ARB
  ARB --> RB --> TX --> LANE_O[/lane_tx/]
  CCQ & CCS --- ARB
  LANE_I[/lane_rx/] --> RX
  RX -->|in-order body| RXQ[/rx_req / rx_rsp FIFO/]
  RXQ -.rptr sync.-> CRED --> TX
  RX -->|ack_seq, nak| RB
  RX -->|freed_cum| CCQ & CCS
  RX -->|good/bad/train info| FSM
  FSM -->|state| TX & ARB
  RX -->|nak request| TX
  RX & RB & FSM --> CNT
```

### 2.1 Pipeline and latency (link cycles)
| Stage | Cycles |
|-------|--------|
| Enqueue from TX FIFO to replay buffer | 1 |
| Flit select + header/CRC (combinational) + serialize | 4 beats (beat 0 registered) |
| Lane fault-injection register stage | 1 |
| Deserialize + CRC check | 4 beats + 1 |
| Push into RX async FIFO | 1 (+ 2-3 cycles of read-domain sync) |

Round trip for an ACK is about 4 (data flit) + 1 + 5 + up to 4 (waiting for the next reverse
flit boundary) + 4 + 1 + 5 ≈ 24 link cycles, well under `REPLAY_TIMEOUT` (128/256).

## 3. Block summary

| Module | Domain | Function |
|--------|--------|----------|
| `common/sync_2ff` | any | 2-flop synchronizer (parameterized width; used only for gray pointers) |
| `common/reset_sync` | any | Async-assert, sync-deassert reset synchronizer |
| `common/async_fifo` | 2 | Cummings-style gray-pointer FIFO, `DEPTH` power of 2, exposes write-domain read count |
| `common/crc16` | – | Combinational parallel CRC-16-CCITT over 112 bits |
| `common/credit_counter` | link | Counter with consume-1 / return-N, bounds asserted |
| `replay_buffer` | link | Circular store of flit bodies indexed by `seq[log2(DEPTH)-1:0]`, three pointers |
| `flit_tx` | link | Flit selection priority, header fill, CRC, serializer |
| `flit_rx` | link | Deserializer, CRC/type/pattern check, sequence check, NAK request |
| `link_training_fsm` | link | Training/retrain/fail state machine, error window |
| `link_layer` | link | Integrates the above + VC arbiter + credit accumulators + counters |
| `axi_slave_adapter` | axi_a | AXI4 slave → REQ flit bodies; RSP flit bodies → B/R |
| `axi_master_adapter` | axi_b | REQ flit bodies → AXI4 master; B/R → RSP flit bodies |
| `apb_csr` | axi | Registers, snapshot shadowing, IRQ |
| `lane_fault_inj` | link | XOR/drop injection + 1 register stage (verification top only) |
| `die_a_top` / `die_b_top` | all | Reset syncs, CDC FIFOs, adapter, CSR, link layer |
| `d2d_system_top` | all | Two dies + two fault injectors |

## 4. Key design decisions
1. **Cumulative ACK and credit fields on every flit.** They need no separate retry, and a lost
   flit can never leak a credit or an ACK. Increment-style credit returns would need their own
   reliability mechanism.
2. **The RX VC buffer is the CDC FIFO.** The credit return comes straight from the FIFO read
   pointer that is already synchronized into the link domain, so the design adds no extra
   crossing.
3. **Credits are consumed at enqueue into the replay buffer**, not when a flit is sent, so
   replays are credit-neutral.
4. **Header fields are filled at send time**, so replayed flits carry fresh ACK/credit values.
   The replay buffer stores only the 80-bit body. The SEQ of the flit being sent is `rd_seq`
   itself, and the storage index is `rd_seq[log2(DEPTH)-1:0]`.
5. **Strict in-order AXI execution at Die B.** This keeps the ordering proof trivial and the
   scoreboard exact. It is a deliberate scope reduction: throughput is traded for an exact ordering model.
