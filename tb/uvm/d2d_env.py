"""pyuvm environment for d2d_system_top.

Structure (UVM):
  D2dEnv
   +- AxiMasterAgent  (Die A host: sequencer, driver, monitor, response-ready driver)
   +- AxiMemAgent     (Die B memory: reactive driver + monitor)
   +- ApbAgent x2     (sequencer, driver)
   +- LaneFaultAgent x2 (a2b carries the REQ VC, b2a carries the RSP VC)
   +- D2dScoreboard   (reference memory, ordering, loss/duplication checks)
   +- D2dCoverage     (cocotb-coverage, sampled from monitors and DUT probes)
All BFMs are per-cycle state machines so a mid-traffic reset can abort them cleanly.
"""
import json
import os
import random
from collections import deque

import cocotb
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly, Timer
from cocotb_coverage.coverage import CoverPoint, CoverCross, coverage_db
from pyuvm import (uvm_sequence_item, uvm_sequence, uvm_sequencer, uvm_driver, uvm_component,
                   uvm_agent, uvm_env, uvm_analysis_port, uvm_subscriber, ConfigDB)

ST_NAMES = {0: "RESET", 1: "TRAIN", 2: "ACTIVE", 3: "RETRAIN", 4: "FAILED"}


def mem_default(addr):
    """Deterministic content of never-written memory (shared by DUT memory and model)."""
    return (addr * 0x9E3779B97F4A7C15 + 0x1234567) & ((1 << 64) - 1)


def strb_merge(old, new, strb):
    out = old
    for b in range(8):
        if (strb >> b) & 1:
            mask = 0xFF << (8 * b)
            out = (out & ~mask) | (new & mask)
    return out


# =============================================================================== coverage
def wstrb_kind(s):
    if s == 0xFF:
        return "full"
    if s == 0:
        return "zero"
    if bin(s).count("1") == 1:
        return "single"
    return "sparse"


@CoverPoint("d2d.axi.kind", xf=lambda t: t.kind, bins=["rd", "wr"])
@CoverPoint("d2d.axi.len", xf=lambda t: t.length, bins=list(range(1, 17)))
@CoverPoint("d2d.axi.id", xf=lambda t: t.id, bins=list(range(16)))
@CoverPoint("d2d.axi.idgrp", xf=lambda t: t.id >> 2, bins=[0, 1, 2, 3])
@CoverCross("d2d.axi.len_x_idgrp", items=["d2d.axi.len", "d2d.axi.idgrp"])
@CoverCross("d2d.axi.kind_x_id", items=["d2d.axi.kind", "d2d.axi.id"])
def cov_axi_txn(t):
    pass


@CoverPoint("d2d.axi.wstrb", xf=lambda s: wstrb_kind(s), bins=["full", "zero", "single", "sparse"])
def cov_wstrb(s):
    pass


@CoverPoint("d2d.axi.outstanding", xf=lambda k, n: (k, n),
            bins=[(k, n) for k in ("wr", "rd") for n in range(1, 5)])
def cov_outstanding(k, n):
    pass


@CoverPoint("d2d.link.credit_stall", xf=lambda vc: vc, bins=["REQ", "RSP"])
def cov_credit_stall(vc):
    pass


def _depth_bin(d):
    return "1" if d <= 1 else "2-4" if d <= 4 else "5-8" if d <= 8 else "9-16"


@CoverPoint("d2d.link.replay_depth", xf=lambda d: _depth_bin(d), bins=["1", "2-4", "5-8", "9-16"])
def cov_replay_depth(d):
    pass


@CoverPoint("d2d.link.recovery", xf=lambda r: r, bins=["NAK", "TIMEOUT", "RETRAIN"])
def cov_recovery(r):
    pass


LTSSM_ARCS = [("RESET", "TRAIN"), ("TRAIN", "ACTIVE"), ("ACTIVE", "RETRAIN"), ("RETRAIN", "ACTIVE"),
              ("TRAIN", "FAILED"), ("RETRAIN", "FAILED"), ("ACTIVE", "FAILED"), ("FAILED", "RESET"),
              ("ACTIVE", "RESET"), ("TRAIN", "RESET"), ("RETRAIN", "RESET")]


@CoverPoint("d2d.ltssm.state", xf=lambda s: s, bins=list(ST_NAMES.values()))
def cov_ltssm_state(s):
    pass


@CoverPoint("d2d.ltssm.arc", xf=lambda a, b: (a, b), bins=LTSSM_ARCS)
def cov_ltssm_arc(a, b):
    pass


CSR_NAMES = ["CTRL", "STATUS", "CRC_ERR_CNT", "NAK_CNT", "REPLAY_CNT", "TIMEOUT_CNT", "RETRAIN_CNT",
             "ERR_CFG", "ERR_WINDOW", "IRQ_EN", "IRQ_STATUS", "ID"]
CSR_ADDR = {n: 4 * i for i, n in enumerate(CSR_NAMES)}


@CoverPoint("d2d.csr.reg", xf=lambda r, w: r, bins=CSR_NAMES + ["UNMAPPED"])
@CoverPoint("d2d.csr.dir", xf=lambda r, w: "W" if w else "R", bins=["R", "W"])
@CoverCross("d2d.csr.reg_x_dir", items=["d2d.csr.reg", "d2d.csr.dir"])
def cov_csr(r, w):
    pass


@CoverPoint("d2d.fault.type", xf=lambda t, vc: t, bins=["single", "multi", "beat", "burst", "drop"])
@CoverPoint("d2d.fault.vc", xf=lambda t, vc: vc, bins=["REQ", "RSP"])
@CoverCross("d2d.fault.type_x_vc", items=["d2d.fault.type", "d2d.fault.vc"])
def cov_fault(t, vc):
    pass


@CoverPoint("d2d.cdc.clk_ratio", xf=lambda r: r, bins=["link_fastest", "axi_a_fastest", "axi_b_fastest", "near_equal"])
def cov_clk_ratio(r):
    pass


def dump_coverage(path):
    """Write per-bin hit counts of every leaf coverage item to JSON (merged by scripts/report.py)."""
    out = {}
    for name, item in coverage_db.items():
        det = getattr(item, "detailed_coverage", None)
        # only leaf items (CoverPoint / CoverCross) map bins to integer hit counts
        if isinstance(det, dict) and det and all(isinstance(v, int) for v in det.values()):
            out[name] = {repr(k): int(v) for k, v in det.items()}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(out, f, indent=1)


# =============================================================================== items
class AxiItem(uvm_sequence_item):
    def __init__(self, name="axi_item"):
        super().__init__(name)
        self.kind = "wr"
        self.id = 0
        self.addr = 0
        self.length = 1
        self.data = []
        self.strb = []
        self.resp_data = []
        self.resp = 0

    def randomize(self, kinds=("rd", "wr"), max_len=16, addr_space=0x10000, len_choice=None):
        self.kind = random.choice(kinds)
        self.id = random.randrange(16)
        self.length = len_choice if len_choice else random.randint(1, max_len)
        while True:
            self.addr = random.randrange(0, addr_space, 8)
            if (self.addr & 0xFFF) + 8 * self.length <= 0x1000:  # no 4 KB crossing
                break
        if self.kind == "wr":
            self.data = [random.getrandbits(64) for _ in range(self.length)]
            self.strb = [random.choice([0xFF, 0xFF, random.getrandbits(8), 1 << random.randrange(8), 0])
                         for _ in range(self.length)]

    def key(self):
        return (self.kind, self.id, self.addr, self.length, tuple(self.data), tuple(self.strb))

    def __str__(self):
        return f"{self.kind} id={self.id} addr={self.addr:#x} len={self.length}"


class ApbItem(uvm_sequence_item):
    def __init__(self, name="apb_item", addr=0, write=False, wdata=0):
        super().__init__(name)
        self.addr = addr
        self.write = write
        self.wdata = wdata
        self.rdata = 0
        self.slverr = 0


# =============================================================================== AXI master (Die A)
class AxiMasterDriver(uvm_driver):
    """Drives AW+W or AR for each item (random VALID gaps). Does not wait for the
    response, so up to 4 transactions can be outstanding inside the DUT."""

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")
        self.cfg = ConfigDB().get(self, "", "CFG")

    async def run_phase(self):
        d = self.dut
        for s in ("s_axi_awvalid", "s_axi_wvalid", "s_axi_arvalid"):
            getattr(d, s).value = 0
        while True:
            item = await self.seq_item_port.get_next_item()
            await self.drive(item)
            self.seq_item_port.item_done()

    async def phase(self, valid, ready, fields):
        """Random idle gap, then present VALID with fields until READY.
        All writes happen at falling edges; READY is sampled in ReadOnly before the
        rising edge that completes the handshake. Returns False if reset aborted it."""
        d = self.dut
        while random.random() < self.cfg.valid_gap:
            valid.value = 0
            await FallingEdge(d.clk_axi_a)
        if self.cfg.reset_epoch != self.epoch:  # a reset happened during this item
            valid.value = 0
            return False
        for sig, v in fields:
            sig.value = v
        valid.value = 1
        while True:
            await ReadOnly()
            hs = int(ready.value)
            await FallingEdge(d.clk_axi_a)
            if not int(d.rst_n.value) or self.cfg.reset_epoch != self.epoch:
                valid.value = 0
                return False
            if hs:
                valid.value = 0
                return True

    async def drive(self, it):
        d = self.dut
        await FallingEdge(d.clk_axi_a)
        while not int(d.rst_n.value):
            await FallingEdge(d.clk_axi_a)
        self.epoch = self.cfg.reset_epoch
        if it.kind == "wr":
            ok = await self.phase(d.s_axi_awvalid, d.s_axi_awready,
                                  [(d.s_axi_awid, it.id), (d.s_axi_awaddr, it.addr),
                                   (d.s_axi_awlen, it.length - 1), (d.s_axi_awsize, 3),
                                   (d.s_axi_awburst, 1)])
            for i in range(it.length):
                if not ok:
                    return
                ok = await self.phase(d.s_axi_wvalid, d.s_axi_wready,
                                      [(d.s_axi_wdata, it.data[i]), (d.s_axi_wstrb, it.strb[i]),
                                       (d.s_axi_wlast, int(i == it.length - 1))])
        else:
            await self.phase(d.s_axi_arvalid, d.s_axi_arready,
                             [(d.s_axi_arid, it.id), (d.s_axi_araddr, it.addr),
                              (d.s_axi_arlen, it.length - 1), (d.s_axi_arsize, 3),
                              (d.s_axi_arburst, 1)])


class AxiReadyDriver(uvm_component):
    """Randomized BREADY/RREADY on Die A (host back-pressure)."""

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")
        self.cfg = ConfigDB().get(self, "", "CFG")

    async def run_phase(self):
        d = self.dut
        while True:
            await FallingEdge(d.clk_axi_a)
            if self.cfg.host_stall_cycles > 0:
                d.s_axi_bready.value = 0
                d.s_axi_rready.value = 0
                self.cfg.host_stall_cycles -= 1
                continue
            d.s_axi_bready.value = int(random.random() < self.cfg.host_ready)
            d.s_axi_rready.value = int(random.random() < self.cfg.host_ready)


class AxiMasterMonitor(uvm_component):
    """Observes Die A: completed requests (in acceptance order) and responses."""

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")
        self.req_ap = uvm_analysis_port("req_ap", self)
        self.rsp_ap = uvm_analysis_port("rsp_ap", self)
        self.wr_out = 0
        self.rd_out = 0

    async def run_phase(self):
        d = self.dut
        pend_w = None
        rbeats = []
        while True:
            # values settled after the falling edge are exactly what the next rising edge samples
            await FallingEdge(d.clk_axi_a)
            await ReadOnly()
            if not int(d.rst_n.value):
                pend_w, rbeats, self.wr_out, self.rd_out = None, [], 0, 0
                continue
            if int(d.s_axi_awvalid.value) and int(d.s_axi_awready.value):
                pend_w = AxiItem("mon_w")
                pend_w.kind, pend_w.id = "wr", int(d.s_axi_awid.value)
                pend_w.addr, pend_w.length = int(d.s_axi_awaddr.value), int(d.s_axi_awlen.value) + 1
                self.wr_out += 1
                cov_outstanding("wr", self.wr_out)
            if int(d.s_axi_wvalid.value) and int(d.s_axi_wready.value):
                assert pend_w is not None, "W beat without AW"
                pend_w.data.append(int(d.s_axi_wdata.value))
                pend_w.strb.append(int(d.s_axi_wstrb.value))
                cov_wstrb(int(d.s_axi_wstrb.value))
                if int(d.s_axi_wlast.value):
                    assert len(pend_w.data) == pend_w.length
                    self.req_ap.write(pend_w)
                    pend_w = None
            if int(d.s_axi_arvalid.value) and int(d.s_axi_arready.value):
                r = AxiItem("mon_r")
                r.kind, r.id = "rd", int(d.s_axi_arid.value)
                r.addr, r.length = int(d.s_axi_araddr.value), int(d.s_axi_arlen.value) + 1
                self.rd_out += 1
                cov_outstanding("rd", self.rd_out)
                self.req_ap.write(r)
            if int(d.s_axi_bvalid.value) and int(d.s_axi_bready.value):
                b = AxiItem("mon_b")
                b.kind, b.id, b.resp = "wr", int(d.s_axi_bid.value), int(d.s_axi_bresp.value)
                self.wr_out -= 1
                self.rsp_ap.write(b)
            if int(d.s_axi_rvalid.value) and int(d.s_axi_rready.value):
                rbeats.append((int(d.s_axi_rdata.value), int(d.s_axi_rid.value), int(d.s_axi_rresp.value)))
                if int(d.s_axi_rlast.value):
                    r = AxiItem("mon_rsp_r")
                    r.kind, r.id = "rd", rbeats[0][1]
                    r.resp_data = [x[0] for x in rbeats]
                    r.resp = max(x[2] for x in rbeats)
                    assert all(x[1] == r.id for x in rbeats), "RID changed inside a burst"
                    self.rd_out -= 1
                    self.rsp_ap.write(r)
                    rbeats = []


class AxiMasterAgent(uvm_agent):
    def build_phase(self):
        self.seqr = uvm_sequencer("seqr", self)
        self.driver = AxiMasterDriver("driver", self)
        self.ready = AxiReadyDriver("ready", self)
        self.monitor = AxiMasterMonitor("monitor", self)

    def connect_phase(self):
        self.driver.seq_item_port.connect(self.seqr.seq_item_export)


# =============================================================================== AXI memory (Die B)
class AxiMemAgent(uvm_component):
    """Reactive AXI4 slave memory on Die B with random READY / response latency.
    Also monitors the request stream seen at Die B (for loss/dup/reorder checks)."""

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")
        self.cfg = ConfigDB().get(self, "", "CFG")
        self.req_ap = uvm_analysis_port("req_ap", self)
        self.mem = {}

    def read(self, a):
        return self.mem.get(a, mem_default(a))

    async def run_phase(self):
        d = self.dut
        outs = ("m_axi_awready", "m_axi_wready", "m_axi_bvalid", "m_axi_arready", "m_axi_rvalid")
        for n in outs:
            getattr(d, n).value = 0
        st, cur, beat, delay, rv_on, cap = "idle", None, 0, 0, False, None
        while True:
            await FallingEdge(d.clk_axi_b)
            if not int(d.rst_n.value):
                st, cur, rv_on, cap = "idle", None, False, None
                for n in outs:
                    getattr(d, n).value = 0
                continue
            # 1. handshakes completed at the rising edge just passed
            if cap:
                if cap["aw"]:
                    cur = AxiItem("memw")
                    cur.kind, cur.id, cur.addr, cur.length = "wr", cap["aw"][0], cap["aw"][1], cap["aw"][2]
                    st, beat = "w", 0
                if cap["ar"]:
                    cur = AxiItem("memr")
                    cur.kind, cur.id, cur.addr, cur.length = "rd", cap["ar"][0], cap["ar"][1], cap["ar"][2]
                    self.req_ap.write(cur)
                    st, beat, delay, rv_on = "r", 0, random.randint(0, self.cfg.mem_latency), False
                if cap["w"]:
                    wd, ws, wl = cap["w"]
                    a = cur.addr + 8 * beat
                    assert wl == int(beat == cur.length - 1), "WLAST mismatch at Die B"
                    cur.data.append(wd)
                    cur.strb.append(ws)
                    self.mem[a] = strb_merge(self.read(a), wd, ws)
                    beat += 1
                    if beat == cur.length:
                        self.req_ap.write(cur)
                        st, delay = "b", random.randint(0, self.cfg.mem_latency)
                if cap["b"]:
                    st = "idle"
                if cap["r"]:
                    beat += 1
                    rv_on = False
                    if beat == cur.length:
                        st = "idle"
            # 2. drive outputs for this cycle
            rnd = lambda: int(random.random() < self.cfg.mem_ready)
            d.m_axi_awready.value = int(st == "idle") & rnd()
            d.m_axi_arready.value = int(st == "idle") & rnd()
            d.m_axi_wready.value = int(st == "w") & rnd()
            if st in ("b", "r") and delay:
                delay -= 1
            d.m_axi_bvalid.value = int(st == "b" and delay == 0)
            d.m_axi_bid.value = cur.id if cur else 0
            d.m_axi_bresp.value = 0
            if st == "r" and delay == 0 and not rv_on and random.random() < self.cfg.mem_ready:
                rv_on = True
            if st == "r":
                a = cur.addr + 8 * beat
                d.m_axi_rid.value = cur.id
                d.m_axi_rdata.value = self.read(a)
                d.m_axi_rresp.value = 0
                d.m_axi_rlast.value = int(beat == cur.length - 1)
            d.m_axi_rvalid.value = int(st == "r" and rv_on)
            # 3. sample what the next rising edge will see
            await ReadOnly()
            cap = {"aw": None, "ar": None, "w": None, "b": False, "r": False}
            if int(d.m_axi_awvalid.value) and int(d.m_axi_awready.value):
                assert int(d.m_axi_awburst.value) == 1 and int(d.m_axi_awsize.value) == 3
                cap["aw"] = (int(d.m_axi_awid.value), int(d.m_axi_awaddr.value), int(d.m_axi_awlen.value) + 1)
            if int(d.m_axi_arvalid.value) and int(d.m_axi_arready.value):
                cap["ar"] = (int(d.m_axi_arid.value), int(d.m_axi_araddr.value), int(d.m_axi_arlen.value) + 1)
            if int(d.m_axi_wvalid.value) and int(d.m_axi_wready.value):
                cap["w"] = (int(d.m_axi_wdata.value), int(d.m_axi_wstrb.value), int(d.m_axi_wlast.value))
            cap["b"] = bool(int(d.m_axi_bvalid.value) and int(d.m_axi_bready.value))
            cap["r"] = bool(int(d.m_axi_rvalid.value) and int(d.m_axi_rready.value))


# =============================================================================== APB
class ApbDriver(uvm_driver):
    def __init__(self, name, parent, prefix):
        super().__init__(name, parent)
        self.prefix = prefix

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")

    def sig(self, n):
        return getattr(self.dut, f"apb_{self.prefix}_{n}")

    async def run_phase(self):
        clk = self.dut.clk_axi_a if self.prefix == "a" else self.dut.clk_axi_b
        self.sig("psel").value = 0
        self.sig("penable").value = 0
        while True:
            it = await self.seq_item_port.get_next_item()
            await FallingEdge(clk)
            self.sig("paddr").value = it.addr
            self.sig("pwrite").value = int(it.write)
            self.sig("pwdata").value = it.wdata
            self.sig("psel").value = 1
            await FallingEdge(clk)
            self.sig("penable").value = 1
            while True:
                await ReadOnly()
                done = int(self.sig("pready").value)
                if done:
                    it.rdata = int(self.sig("prdata").value)
                    it.slverr = int(self.sig("pslverr").value)
                await FallingEdge(clk)
                if done:
                    break
            self.sig("psel").value = 0
            self.sig("penable").value = 0
            name = next((n for n, a in CSR_ADDR.items() if a == it.addr), "UNMAPPED")
            cov_csr(name, it.write)
            self.seq_item_port.item_done()


class ApbAgent(uvm_agent):
    def __init__(self, name, parent, prefix):
        super().__init__(name, parent)
        self.prefix = prefix

    def build_phase(self):
        self.seqr = uvm_sequencer("seqr", self)
        self.driver = ApbDriver("driver", self, self.prefix)

    def connect_phase(self):
        self.driver.seq_item_port.connect(self.seqr.seq_item_export)


# =============================================================================== lane faults
class LaneFaultAgent(uvm_component):
    """Flit-aligned fault injection on one lane direction. Error types stay within the
    CRC-16 guaranteed detection envelope (<=3 random bit flips, bursts <=16 bits):
    an undetectable pattern would be a residual-error-rate event, not a design bug."""

    TYPES = ("single", "multi", "beat", "burst", "drop")

    def __init__(self, name, parent, direction):
        super().__init__(name, parent)
        self.direction = direction  # "a2b" (REQ VC) or "b2a" (RSP VC)
        self.vc = "REQ" if direction == "a2b" else "RSP"
        self.rate = 0.0
        self.types = list(self.TYPES)
        self.injected = {t: 0 for t in self.TYPES}

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")

    def pattern(self, t):
        """Returns per-beat (xor, drop) list for one flit."""
        beats = [(0, 0)] * 4
        b = random.randrange(4)
        if t == "single":
            beats[b] = (1 << random.randrange(32), 0)
        elif t == "multi":
            m = 0
            for bit in random.sample(range(32), random.choice([2, 3])):
                m |= 1 << bit
            beats[b] = (m, 0)
        elif t == "beat":  # corrupt a 16-bit field of one beat with a random pattern
            beats[b] = ((random.getrandbits(16) | 1) << random.choice([0, 16]), 0)
        elif t == "burst":
            n = random.randint(2, 16)
            pos = random.randint(0, 32 - n)
            m = ((1 << n) - 1) & ~(random.getrandbits(n) & ~(1 | (1 << (n - 1))))
            beats[b] = (m << pos, 0)
        else:
            beats = [(0, 1)] * 4
        return beats

    async def run_phase(self):
        d = self.dut
        xor = getattr(d, f"fi_{self.direction}_xor")
        drop = getattr(d, f"fi_{self.direction}_drop")
        sof = getattr(d, f"mon_{self.direction}_sof")
        xor.value = 0
        drop.value = 0
        sched = []
        while True:
            await FallingEdge(d.clk_link)
            if not sched and int(sof.value) and self.rate > 0 and random.random() < self.rate:
                t = random.choice(self.types)
                self.injected[t] += 1
                cov_fault(t, self.vc)
                sched = self.pattern(t)
            x, dr = sched.pop(0) if sched else (0, 0)
            xor.value = x
            drop.value = dr

    def total(self):
        return sum(self.injected.values())


# =============================================================================== scoreboard
class _Imp(uvm_subscriber):
    def __init__(self, name, parent, fn):
        super().__init__(name, parent)
        self.fn = fn

    def write(self, t):
        self.fn(t)


class D2dScoreboard(uvm_component):
    """End-to-end checker. Execution is strictly in order (spec 5.3), so the expected
    response stream is exact: one entry per request in Die A acceptance order."""

    def build_phase(self):
        self.a_req = _Imp("a_req", self, self.on_a_req)
        self.a_rsp = _Imp("a_rsp", self, self.on_a_rsp)
        self.b_req = _Imp("b_req", self, self.on_b_req)
        self.ref = {}
        self.exp_rsp = deque()
        self.exp_b_req = deque()
        self.n_req = self.n_rsp = self.n_b_req = 0
        self.n_flushed = 0  # transactions destroyed by a mid-test reset (never complete)
        self.errors = []

    def ref_read(self, a):
        return self.ref.get(a, mem_default(a))

    def resync(self, mem):
        """After a reset, aborted transactions may or may not have executed at Die B:
        re-baseline the reference model from the memory and drop expectations."""
        self.ref = dict(mem)
        self.n_flushed += len(self.exp_rsp)
        self.exp_rsp.clear()
        self.exp_b_req.clear()

    def err(self, msg):
        self.errors.append(msg)
        self.logger.error(msg)

    def on_a_req(self, t):
        self.n_req += 1
        cov_axi_txn(t)
        self.exp_b_req.append(t.key())
        if t.kind == "wr":
            for i in range(t.length):
                a = t.addr + 8 * i
                self.ref[a] = strb_merge(self.ref_read(a), t.data[i], t.strb[i])
            self.exp_rsp.append(("wr", t.id, None))
        else:
            self.exp_rsp.append(("rd", t.id, [self.ref_read(t.addr + 8 * i) for i in range(t.length)]))

    def on_b_req(self, t):
        self.n_b_req += 1
        if not self.exp_b_req:
            self.err(f"Die B saw an unexpected (duplicated?) request: {t}")
            return
        exp = self.exp_b_req.popleft()
        if exp != t.key():
            self.err(f"Die B request mismatch (loss/reorder/corruption): got {t} exp {exp[:4]}")

    def on_a_rsp(self, t):
        self.n_rsp += 1
        if not self.exp_rsp:
            self.err(f"unexpected response {t.kind} id={t.id}")
            return
        kind, rid, data = self.exp_rsp.popleft()
        if kind != t.kind or rid != t.id or t.resp != 0:
            self.err(f"response mismatch: got {t.kind} id={t.id} resp={t.resp} exp {kind} id={rid}")
        elif kind == "rd" and data != t.resp_data:
            bad = next(i for i in range(len(data)) if i >= len(t.resp_data) or data[i] != t.resp_data[i])
            self.err(f"read data mismatch id={rid} beat {bad}")

    def pending(self):
        return len(self.exp_rsp)

    def check_phase(self):
        if self.exp_rsp:
            self.err(f"{len(self.exp_rsp)} transactions never completed (lost)")
        if self.exp_b_req:
            self.err(f"{len(self.exp_b_req)} requests never reached Die B")


# =============================================================================== DUT probes for coverage
class LinkProbe(uvm_component):
    """Samples link-internal events for coverage and fault accounting."""

    def build_phase(self):
        self.dut = ConfigDB().get(self, "", "DUT")
        self.arcs = set()
        self.states_seen = {"a": set(), "b": set()}

    async def run_phase(self):
        d = self.dut
        la, lb = d.u_die_a.u_link, d.u_die_b.u_link
        prev = {"a": 0, "b": 0}
        while True:
            await RisingEdge(d.clk_link)
            await ReadOnly()
            for tag, ll in (("a", la), ("b", lb)):
                s = int(ll.link_state.value)
                if s != prev[tag]:
                    cov_ltssm_arc(ST_NAMES[prev[tag]], ST_NAMES[s])
                    self.arcs.add((tag, ST_NAMES[prev[tag]], ST_NAMES[s]))
                    if s == 3:
                        cov_recovery("RETRAIN")
                    prev[tag] = s
                cov_ltssm_state(ST_NAMES[s])
                self.states_seen[tag].add(ST_NAMES[s])
                if int(ll.rewind_moved.value):
                    depth = (int(ll.wr_seq.value) - int(ll.ack_ptr.value)) & 0xFF
                    cov_replay_depth(depth)
                    if int(ll.nak_rcvd.value):
                        cov_recovery("NAK")
                    elif int(ll.replay_timeout.value):
                        cov_recovery("TIMEOUT")
            if int(la.cand_req.value) == 0 and int(la.tx_req_empty.value) == 0 and int(la.cq_avail.value) == 0:
                cov_credit_stall("REQ")
            if int(lb.tx_rsp_empty.value) == 0 and int(lb.cs_avail.value) == 0:
                cov_credit_stall("RSP")


# =============================================================================== env
class EnvCfg:
    def __init__(self):
        self.valid_gap = 0.2      # probability of an idle cycle before each VALID
        self.host_ready = 0.9     # BREADY/RREADY probability
        self.host_stall_cycles = 0
        self.mem_ready = 0.8      # Die B memory READY probability
        self.mem_latency = 4      # max response latency (clk_axi_b cycles)
        self.reset_epoch = 0      # incremented by tests on every mid-test reset


class D2dEnv(uvm_env):
    def build_phase(self):
        self.cfg = EnvCfg()
        ConfigDB().set(None, "*", "CFG", self.cfg)
        self.axi = AxiMasterAgent("axi_a", self)
        self.mem = AxiMemAgent("mem_b", self)
        self.apb_a = ApbAgent("apb_a", self, "a")
        self.apb_b = ApbAgent("apb_b", self, "b")
        self.fi_a2b = LaneFaultAgent("fi_a2b", self, "a2b")
        self.fi_b2a = LaneFaultAgent("fi_b2a", self, "b2a")
        self.sb = D2dScoreboard("sb", self)
        self.probe = LinkProbe("probe", self)

    def connect_phase(self):
        self.axi.monitor.req_ap.connect(self.sb.a_req.analysis_export)
        self.axi.monitor.rsp_ap.connect(self.sb.a_rsp.analysis_export)
        self.mem.req_ap.connect(self.sb.b_req.analysis_export)


# =============================================================================== sequences
class AxiRandomSeq(uvm_sequence):
    def __init__(self, name="axi_rand", n=50, **kw):
        super().__init__(name)
        self.n = n
        self.kw = kw

    async def body(self):
        for _ in range(self.n):
            it = AxiItem("it")
            await self.start_item(it)
            it.randomize(**self.kw)
            await self.finish_item(it)


class ApbSeq(uvm_sequence):
    """Executes a list of (addr, write, wdata) and stores the completed items."""

    def __init__(self, name="apb", ops=()):
        super().__init__(name)
        self.ops = list(ops)
        self.results = []

    async def body(self):
        for addr, write, wdata in self.ops:
            it = ApbItem("apb", addr, write, wdata)
            await self.start_item(it)
            await self.finish_item(it)
            self.results.append(it)
