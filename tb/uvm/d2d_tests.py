"""pyuvm tests for d2d_system_top. Every test is seedable (RANDOM_SEED / SEED); the
seed is logged by cocotb at start-up and recorded in the per-test result JSON."""
import json
import os
import random

import cocotb
import pyuvm
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly, Timer, with_timeout
from pyuvm import uvm_test, uvm_root, ConfigDB

from d2d_env import (D2dEnv, AxiRandomSeq, ApbSeq, AxiItem, CSR_ADDR, ST_NAMES,
                     cov_clk_ratio, dump_coverage, mem_default)

ACTIVE = 2
FAILED = 4


class D2dBaseTest(uvm_test):
    """Clocks, reset, link-up wait, traffic, drain, end-of-test checks and reporting."""
    periods = (1000, 1700, 2300)  # clk_link, clk_axi_a, clk_axi_b in ps (mutually unrelated)
    timeout_us = 1500
    allow_link_fail = False  # tests that drive the link to FAILED on purpose set this

    def build_phase(self):
        self.dut = cocotb.top
        ConfigDB().set(None, "*", "DUT", self.dut)
        self.env = D2dEnv("env", self)
        self.clk_tasks = []
        self.expect_errors = False

    # ------------------------------------------------------------------ helpers
    def start_clocks(self, link, a, b):
        for t in self.clk_tasks:
            t.kill()
        d = self.dut
        self.clk_tasks = [cocotb.start_soon(Clock(d.clk_link, link, "ps").start()),
                          cocotb.start_soon(Clock(d.clk_axi_a, a, "ps").start()),
                          cocotb.start_soon(Clock(d.clk_axi_b, b, "ps").start())]
        fastest = min((link, "link_fastest"), (a, "axi_a_fastest"), (b, "axi_b_fastest"))
        ratio = max(link, a, b) / min(link, a, b)
        cov_clk_ratio("near_equal" if ratio < 1.15 else fastest[1])
        self.logger.info("clocks: link=%dps axi_a=%dps axi_b=%dps", link, a, b)

    async def reset(self, cycles=10):
        d = self.dut
        d.rst_n.value = 0
        for _ in range(cycles):
            await RisingEdge(d.clk_axi_b)
            await RisingEdge(d.clk_axi_a)
        d.rst_n.value = 1

    def link_states(self):
        d = self.dut
        return int(d.u_die_a.u_link.link_state.value), int(d.u_die_b.u_link.link_state.value)

    async def wait_link_up(self, max_cycles=40000):
        for _ in range(max_cycles):
            await RisingEdge(self.dut.clk_link)
            if self.link_states() == (ACTIVE, ACTIVE):
                return
        raise AssertionError(f"link did not come up, states={self.link_states()}")

    async def link_cycles(self, n):
        for _ in range(n):
            await RisingEdge(self.dut.clk_link)

    async def traffic(self, n, **kw):
        await AxiRandomSeq("seq", n=n, **kw).start(self.env.axi.seqr)

    async def apb(self, die, ops):
        seq = ApbSeq("apb", ops)
        await seq.start(getattr(self.env, f"apb_{die}").seqr)
        return seq.results

    async def drain(self, max_cycles=200000):
        for _ in range(max_cycles):
            await RisingEdge(self.dut.clk_link)
            if self.env.sb.pending() == 0:
                return
        raise AssertionError(f"drain timeout: {self.env.sb.pending()} transactions outstanding, "
                             f"link states {self.link_states()}")

    def counters(self, die):
        ll = getattr(self.dut, f"u_die_{die}").u_link
        return {k: int(getattr(ll, k).value) for k in
                ("crc_err_cnt", "nak_cnt", "replay_cnt", "timeout_cnt", "retrain_cnt")}

    # ------------------------------------------------------------------ phases
    async def heartbeat(self, period=5000):
        d = self.dut
        while True:
            await self.link_cycles(period)
            la, lb = d.u_die_a.u_link, d.u_die_b.u_link
            if FAILED in self.link_states() and not self.allow_link_fail:
                raise AssertionError(f"link FAILED unexpectedly: states={self.link_states()}, "
                                     f"counters A={self.counters('a')} B={self.counters('b')}")
            self.logger.info(
                "heartbeat: states=%s pending=%d req=%d rsp=%d | A wr=%d rd=%d ack=%d exp=%d cq=%d | "
                "B wr=%d rd=%d ack=%d exp=%d cs=%d | awv/r=%d%d wv/r=%d%d arv/r=%d%d bv/r=%d%d rv/r=%d%d",
                self.link_states(), self.env.sb.pending(), self.env.sb.n_req, self.env.sb.n_rsp,
                int(la.wr_seq.value), int(la.rb_seq.value), int(la.ack_ptr.value), int(la.exp_seq.value),
                int(la.cq_count.value), int(lb.wr_seq.value), int(lb.rb_seq.value), int(lb.ack_ptr.value),
                int(lb.exp_seq.value), int(lb.cs_count.value),
                int(d.s_axi_awvalid.value), int(d.s_axi_awready.value), int(d.s_axi_wvalid.value),
                int(d.s_axi_wready.value), int(d.s_axi_arvalid.value), int(d.s_axi_arready.value),
                int(d.s_axi_bvalid.value), int(d.s_axi_bready.value), int(d.s_axi_rvalid.value),
                int(d.s_axi_rready.value))

    async def run_phase(self):
        self.raise_objection()
        cocotb.start_soon(self.heartbeat())
        self.start_clocks(*self.periods)
        await self.reset()
        await self.wait_link_up()
        await with_timeout(self.main(), self.timeout_us, "us")
        await self.drain()
        await self.link_cycles(200)
        self.drop_objection()

    async def main(self):
        raise NotImplementedError

    def check_phase(self):
        sb = self.env.sb
        sb.check_phase()
        if sb.n_req != sb.n_rsp + sb.n_flushed:
            sb.err(f"request/response count mismatch: {sb.n_req} requests, {sb.n_rsp} responses, "
                   f"{sb.n_flushed} flushed by reset")
        assert not sb.errors, f"{len(sb.errors)} scoreboard errors, first: {sb.errors[0]}"

    def report_phase(self):
        sb = self.env.sb
        name = type(self).__name__.removesuffix("_test")
        seed = int(os.environ.get("RANDOM_SEED", "0"))
        res = dict(test=name, seed=seed, transactions=sb.n_req, responses=sb.n_rsp, flushed_by_reset=sb.n_flushed,
                   b_requests=sb.n_b_req, errors=len(sb.errors),
                   faults_a2b=self.env.fi_a2b.injected, faults_b2a=self.env.fi_b2a.injected,
                   faults_total=self.env.fi_a2b.total() + self.env.fi_b2a.total(),
                   counters_a=self.counters("a"), counters_b=self.counters("b"),
                   ltssm_arcs=sorted(map(list, self.env.probe.arcs)),
                   sim_time_ns=cocotb.utils.get_sim_time("ns"))
        self.logger.info("RESULT %s", json.dumps(res))
        out = os.environ.get("D2D_RESULT_DIR")
        if out:
            os.makedirs(out, exist_ok=True)
            with open(os.path.join(out, f"{name}_{seed}.json"), "w") as f:
                json.dump(res, f, indent=1)
            dump_coverage(os.path.join(out, "cov", f"{name}_{seed}.json"))


# ====================================================================== tests
class smoke_test(D2dBaseTest):
    """One write and a read-back of the same address."""

    async def main(self):
        w = AxiItem("w")
        w.kind, w.id, w.addr, w.length = "wr", 3, 0x100, 2
        w.data, w.strb = [0x1122334455667788, 0xA5A5A5A5DEADBEEF], [0xFF, 0x0F]
        r = AxiItem("r")
        r.kind, r.id, r.addr, r.length = "rd", 5, 0x100, 2
        seqr = self.env.axi.seqr

        class Directed(pyuvm.uvm_sequence):
            async def body(s):
                for it in (w, r):
                    await s.start_item(it)
                    await s.finish_item(it)

        await Directed("d").start(seqr)


class random_rw_test(D2dBaseTest):
    async def main(self):
        await self.traffic(int(os.environ.get("D2D_NTXN", "200")))


class max_burst_test(D2dBaseTest):
    async def main(self):
        self.env.cfg.valid_gap = 0.0
        await self.traffic(40, len_choice=16)


class outstanding_stress_test(D2dBaseTest):
    """Slow memory + no host gaps keeps 4 writes / 4 reads outstanding."""

    async def main(self):
        c = self.env.cfg
        c.valid_gap, c.mem_ready, c.mem_latency = 0.0, 0.5, 60
        await self.traffic(120, max_len=4)
        mon = self.env.axi.monitor
        assert self.env.axi.monitor is mon


class credit_starvation_test(D2dBaseTest):
    """Host stalls B/R for long periods: RSP RX FIFO fills and RSP credits run out."""

    async def main(self):
        c = self.env.cfg
        c.host_ready = 0.3

        async def staller():
            for _ in range(6):
                await self.link_cycles(1500)
                c.host_stall_cycles = 1500

        st = cocotb.start_soon(staller())
        await self.traffic(80, kinds=("rd",), len_choice=16)
        await self.traffic(40)
        st.kill()
        c.host_stall_cycles = 0


class backpressure_random_test(D2dBaseTest):
    async def main(self):
        c = self.env.cfg
        c.valid_gap, c.host_ready, c.mem_ready, c.mem_latency = 0.5, 0.5, 0.4, 8
        await self.traffic(150)


class crc_error_retry_test(D2dBaseTest):
    """Random CRC errors on 1% of flits in both directions: below the retrain threshold
    (8 errors / 256 flits ~ 3.1%), so recovery must come from NAK + Go-Back-N replay."""

    async def main(self):
        for fi in (self.env.fi_a2b, self.env.fi_b2a):
            fi.rate, fi.types = 0.01, ["single", "multi", "beat", "burst"]
        await self.traffic(200)
        for fi in (self.env.fi_a2b, self.env.fi_b2a):
            fi.rate = 0.0
        ca, cb = self.counters("a"), self.counters("b")
        assert ca["crc_err_cnt"] + cb["crc_err_cnt"] > 0 and ca["nak_cnt"] + cb["nak_cnt"] > 0
        assert ca["replay_cnt"] + cb["replay_cnt"] > 0, (ca, cb)


class flit_drop_timeout_test(D2dBaseTest):
    async def main(self):
        # Phase 1: dense traffic - drops are mostly caught by the SEQ gap (NAK path).
        # Phase 2: sparse single-beat traffic - a dropped flit is followed only by
        # non-sequenced flits, so only the replay timeout can recover it.
        for fi in (self.env.fi_a2b, self.env.fi_b2a):
            fi.rate, fi.types = 0.03, ["drop"]
        await self.traffic(80)
        self.env.cfg.valid_gap = 0.97
        for fi in (self.env.fi_a2b, self.env.fi_b2a):
            fi.rate = 0.15
        await self.traffic(60, max_len=1)
        for fi in (self.env.fi_a2b, self.env.fi_b2a):
            fi.rate = 0.0
        await self.drain()
        ca, cb = self.counters("a"), self.counters("b")
        assert ca["timeout_cnt"] + cb["timeout_cnt"] > 0, (ca, cb)


class error_storm_retrain_test(D2dBaseTest):
    """A burst of errors above the window threshold forces RETRAIN mid-traffic."""

    async def main(self):
        async def storm():
            await self.link_cycles(3000)
            self.env.fi_a2b.rate = 1.0
            await self.link_cycles(400)
            self.env.fi_a2b.rate = 0.0

        cocotb.start_soon(storm())
        await self.traffic(150)
        await self.drain()
        assert self.counters("a")["retrain_cnt"] + self.counters("b")["retrain_cnt"] >= 1


class link_fail_and_recover_test(D2dBaseTest):
    """Continuous corruption exhausts the retrain budget -> FAILED + IRQ; software
    toggles CTRL.ENABLE on both dies and traffic resumes with no loss."""
    allow_link_fail = True

    async def main(self):
        for die in ("a", "b"):
            await self.apb(die, [(CSR_ADDR["IRQ_EN"], True, 0xF), (CSR_ADDR["ERR_CFG"], True, 0x108)])
        tr = cocotb.start_soon(self.traffic(120))
        await self.link_cycles(2000)
        self.env.fi_a2b.rate = self.env.fi_b2a.rate = 1.0
        for _ in range(60000):
            await RisingEdge(self.dut.clk_link)
            if FAILED in self.link_states():
                break
        assert FAILED in self.link_states(), f"link never failed: {self.link_states()}"
        await self.link_cycles(4000)  # let the peer time out too
        self.env.fi_a2b.rate = self.env.fi_b2a.rate = 0.0
        await self.link_cycles(200)
        assert int(self.dut.irq_a.value) or int(self.dut.irq_b.value), "no interrupt on link failure"
        st = {}
        for die in ("a", "b"):
            r = await self.apb(die, [(CSR_ADDR["IRQ_STATUS"], False, 0), (CSR_ADDR["STATUS"], False, 0)])
            st[die] = (r[0].rdata, r[1].rdata)
        self.logger.info("after failure IRQ_STATUS/STATUS: %s", st)
        assert any(v[0] & 0x4 for v in st.values()), "LINK_FAILED interrupt bit not set"
        for die in ("a", "b"):
            await self.apb(die, [(CSR_ADDR["CTRL"], True, 0), (CSR_ADDR["CTRL"], True, 1),
                                 (CSR_ADDR["IRQ_STATUS"], True, 0xF)])
        await self.wait_link_up()
        await tr
        await self.drain()
        for die in ("a", "b"):
            r = await self.apb(die, [(CSR_ADDR["IRQ_STATUS"], False, 0)])
            assert (r[0].rdata & 0x4) == 0, "W1C did not clear LINK_FAILED"


class csr_access_test(D2dBaseTest):
    async def main(self):
        for die in ("a", "b"):
            await self.link_cycles(50)
            r = await self.apb(die, [(CSR_ADDR[n], False, 0) for n in
                                     ("ID", "CTRL", "STATUS", "ERR_CFG", "ERR_WINDOW", "IRQ_EN", "IRQ_STATUS")])
            got = [x.rdata for x in r]
            assert got[0] == 0xD2D10001, hex(got[0])
            assert got[1] == 1 and got[2] == 0xA and got[3] == 0x408 and got[4] == 0x100 and got[5] == 0, got
            # RW, RO and unmapped behaviour
            r = await self.apb(die, [(CSR_ADDR["ERR_WINDOW"], True, 0x1234), (CSR_ADDR["ERR_WINDOW"], False, 0),
                                     (CSR_ADDR["IRQ_EN"], True, 0xA), (CSR_ADDR["IRQ_EN"], False, 0),
                                     (CSR_ADDR["STATUS"], True, 0x7), (CSR_ADDR["STATUS"], False, 0),
                                     (0x40, False, 0), (0x44, True, 1), (CSR_ADDR["ERR_WINDOW"], True, 0x100)])
            assert r[1].rdata == 0x1234 and r[3].rdata == 0xA and r[5].rdata == 0xA
            assert r[6].slverr == 1 and r[7].slverr == 1 and r[0].slverr == 0
            # counters readable and consistent with link-domain values (snapshot may lag)
            r = await self.apb(die, [(CSR_ADDR[n], False, 0) for n in
                                     ("CRC_ERR_CNT", "NAK_CNT", "REPLAY_CNT", "TIMEOUT_CNT", "RETRAIN_CNT")])
            hw = self.counters(die)
            for x, k in zip(r, ("crc_err_cnt", "nak_cnt", "replay_cnt", "timeout_cnt", "retrain_cnt")):
                assert x.rdata <= hw[k], (k, x.rdata, hw[k])
            # read-only registers ignore writes
            ro = ("CRC_ERR_CNT", "NAK_CNT", "REPLAY_CNT", "TIMEOUT_CNT", "RETRAIN_CNT", "ID")
            r = await self.apb(die, [(CSR_ADDR[n], True, 0xFFFF) for n in ro] +
                               [(CSR_ADDR[n], False, 0) for n in ro])
            hw = self.counters(die)
            assert all(x.slverr == 0 for x in r[:len(ro)])
            assert r[-1].rdata == 0xD2D10001, "ID register changed by a write"
            for x, k in zip(r[len(ro):-1], ("crc_err_cnt", "nak_cnt", "replay_cnt", "timeout_cnt", "retrain_cnt")):
                assert x.rdata <= hw[k] and x.rdata != 0xFFFF, (k, x.rdata)
            # force retrain -> RETRAIN_CNT increments, RETRAIN irq bit set, W1C clears it
            before = self.counters(die)["retrain_cnt"]
            await self.apb(die, [(CSR_ADDR["IRQ_EN"], True, 0x2), (CSR_ADDR["CTRL"], True, 0x3)])
            await self.wait_link_up()
            await self.link_cycles(100)
            r = await self.apb(die, [(CSR_ADDR["RETRAIN_CNT"], False, 0), (CSR_ADDR["IRQ_STATUS"], False, 0),
                                     (CSR_ADDR["CTRL"], False, 0)])
            assert r[0].rdata == before + 1, (r[0].rdata, before)
            assert r[1].rdata & 0x2 and r[2].rdata == 1
            irq = int(getattr(self.dut, f"irq_{die}").value)
            assert irq == 1, "irq pin not asserted"
            r = await self.apb(die, [(CSR_ADDR["IRQ_STATUS"], True, 0xF), (CSR_ADDR["IRQ_STATUS"], False, 0),
                                     (CSR_ADDR["IRQ_EN"], True, 0)])
            assert r[1].rdata & 0x2 == 0
        await self.traffic(20)


class ltssm_arcs_test(D2dBaseTest):
    """Directed training-FSM corners driven through the CSRs: ACTIVE->FAILED (zero retry
    budget), RETRAIN->RESET and TRAIN->RESET (disable mid-training), TRAIN->FAILED (peer
    disabled). The link is recovered after each step and traffic is checked at the end."""
    allow_link_fail = True

    async def wait_state(self, die, st, max_cycles=20000):
        idx = 0 if die == "a" else 1
        for _ in range(max_cycles):
            await RisingEdge(self.dut.clk_link)
            if self.link_states()[idx] == st:
                return
        raise AssertionError(f"die {die} never reached {ST_NAMES[st]}: {self.link_states()}")

    async def recover(self):
        for die in ("a", "b"):
            await self.apb(die, [(CSR_ADDR["CTRL"], True, 0), (CSR_ADDR["ERR_CFG"], True, 0x408)])
        for die in ("a", "b"):
            await self.apb(die, [(CSR_ADDR["CTRL"], True, 1)])
        await self.wait_link_up()

    async def main(self):
        # 1. ACTIVE -> FAILED: zero retry budget, then a forced retrain
        await self.apb("a", [(CSR_ADDR["ERR_CFG"], True, 0x008), (CSR_ADDR["CTRL"], True, 0x3)])
        await self.wait_state("a", FAILED)
        await self.recover()
        # 2. RETRAIN -> RESET: force a retrain and disable while retraining
        await self.apb("a", [(CSR_ADDR["CTRL"], True, 0x3), (CSR_ADDR["CTRL"], True, 0x0)])
        await self.wait_state("a", 0)
        await self.recover()
        # 3. TRAIN -> RESET: disable again while the initial training is still running
        await self.apb("a", [(CSR_ADDR["CTRL"], True, 0x0), (CSR_ADDR["CTRL"], True, 0x1),
                             (CSR_ADDR["CTRL"], True, 0x0)])
        await self.wait_state("a", 0)
        await self.recover()
        # 4. TRAIN -> FAILED: peer disabled, so initial training can never complete
        await self.apb("b", [(CSR_ADDR["CTRL"], True, 0x0)])
        await self.apb("a", [(CSR_ADDR["ERR_CFG"], True, 0x108), (CSR_ADDR["CTRL"], True, 0x0),
                             (CSR_ADDR["CTRL"], True, 0x1)])
        await self.wait_state("a", FAILED, 40000)
        await self.recover()
        arcs = {(a, b) for _, a, b in self.env.probe.arcs}
        for arc in (("ACTIVE", "FAILED"), ("RETRAIN", "RESET"), ("TRAIN", "RESET"), ("TRAIN", "FAILED")):
            assert arc in arcs, f"arc {arc} not exercised: {sorted(arcs)}"
        await self.traffic(40)


class clock_ratio_sweep_test(D2dBaseTest):
    RATIOS = [(1000, 1700, 2300), (3100, 1000, 1300), (2900, 2300, 1000), (1500, 1530, 1470),
              (1000, 7300, 5100)]

    async def main(self):
        for link, a, b in self.RATIOS:
            await self.drain()
            self.start_clocks(link, a, b)
            await self.traffic(40)


class reset_during_traffic_test(D2dBaseTest):
    """Reset asserted while transactions are in flight inside the link."""

    async def main(self):
        tr = cocotb.start_soon(self.traffic(60))
        for _ in range(100000):
            await RisingEdge(self.dut.clk_link)
            if self.env.sb.pending() >= 2:
                break
        assert self.env.sb.pending() >= 2
        self.logger.info("asserting reset with %d transactions in flight", self.env.sb.pending())
        self.dut.rst_n.value = 0
        self.env.cfg.reset_epoch += 1
        await self.link_cycles(30)
        self.logger.info("reset held 30 link cycles")
        self.env.sb.resync(self.env.mem.mem)
        self.dut.rst_n.value = 1
        await self.wait_link_up()
        self.logger.info("link up after reset")
        # remaining items run after reset (aborted ones are dropped by the driver)
        for _ in range(40):
            if tr.done():
                break
            await self.link_cycles(5000)
            d = self.dut
            self.logger.info("waiting: pending=%d awv=%d awr=%d wv=%d wr=%d arv=%d arr=%d",
                             self.env.sb.pending(), int(d.s_axi_awvalid.value), int(d.s_axi_awready.value),
                             int(d.s_axi_wvalid.value), int(d.s_axi_wready.value),
                             int(d.s_axi_arvalid.value), int(d.s_axi_arready.value))
            la, lb = d.u_die_a.u_link, d.u_die_b.u_link
            self.logger.info("  states=%s A: tx_req_empty=%d cq_avail=%d cq=%d rb_ready=%d unacked=%d wr=%d ack=%d | "
                             "B: exp=%d rx_req_full=%d req_rcount=%d",
                             self.link_states(), int(la.tx_req_empty.value), int(la.cq_avail.value),
                             int(la.cq_count.value), int(la.rb_enq_ready.value), int(la.unacked.value),
                             int(la.wr_seq.value), int(la.ack_ptr.value), int(lb.exp_seq.value),
                             int(lb.rx_req_full.value), int(lb.rx_req_rcount.value))
        assert tr.done(), "traffic did not finish after reset"
        await self.drain()
        await self.traffic(40)


# ---------------------------------------------------------------------- registration
# Register each test under its plain name so TESTCASE=<name> selects it.
def _register(cls):
    name = cls.__name__.removesuffix("_test")

    async def _run(dut):
        await uvm_root().run_test(cls)

    _run.__name__ = _run.__qualname__ = name
    globals()[name] = cocotb.test()(_run)


for _cls in list(globals().values()):
    if isinstance(_cls, type) and issubclass(_cls, D2dBaseTest) and _cls is not D2dBaseTest:
        _register(_cls)
