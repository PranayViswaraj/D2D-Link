"""Unit tests: crc16, async_fifo, credit_counter, sync_2ff, reset_sync."""
import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer, ReadOnly, FallingEdge

from d2d_model import crc16_ccitt
from runner import run, rtl
from pathlib import Path

HERE = Path(__file__).parent


# --------------------------------------------------------------------------- crc16
@cocotb.test()
async def crc16_vs_model(dut):
    """1000 random + corner vectors against the Python CRC model."""
    vecs = [0, (1 << 112) - 1, 1, 1 << 111] + [random.getrandbits(112) for _ in range(1000)]
    for v in vecs:
        dut.data.value = v
        await Timer(1, "ns")
        assert int(dut.crc.value) == crc16_ccitt(v, 112), hex(v)
    dut._log.info("crc16: %d vectors matched", len(vecs))


def test_crc16():
    run("crc16", rtl("crc16.sv"), "test_common", testcase="crc16_vs_model")


# --------------------------------------------------------------------------- async_fifo
async def fifo_traffic(dut, wper, rper, n=2000, wr_bias=0.6, rd_bias=0.6):
    depth = int(dut.DEPTH.value)
    cocotb.start_soon(Clock(dut.wclk, wper, "ps").start())
    cocotb.start_soon(Clock(dut.rclk, rper, "ps").start())
    dut.wr_en.value = 0
    dut.rd_en.value = 0
    dut.wrst_n.value = 0
    dut.rrst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.wclk)
        await RisingEdge(dut.rclk)
    dut.wrst_n.value = 1
    dut.rrst_n.value = 1
    expected = []
    state = dict(sent=0, recv=0, max_occ=0, saw_full=False)

    async def writer():
        while state["sent"] < n:
            await FallingEdge(dut.wclk)
            if random.random() < wr_bias and not int(dut.full.value):
                d = random.getrandbits(int(dut.W.value))
                dut.wdata.value = d
                dut.wr_en.value = 1
                expected.append(d)
                state["sent"] += 1
            else:
                dut.wr_en.value = 0
                if int(dut.full.value):
                    state["saw_full"] = True
        await FallingEdge(dut.wclk)
        dut.wr_en.value = 0

    async def reader():
        while state["recv"] < n:
            await FallingEdge(dut.rclk)
            if random.random() < rd_bias and not int(dut.empty.value):
                got = int(dut.rdata.value)
                assert expected, "read data that was never written"
                exp = expected.pop(0)
                assert got == exp, f"data mismatch got {got:x} exp {exp:x}"
                dut.rd_en.value = 1
                state["recv"] += 1
            else:
                dut.rd_en.value = 0
            state["max_occ"] = max(state["max_occ"], len(expected))
            assert len(expected) <= depth + 1  # +1: the in-flight write of this cycle
        await FallingEdge(dut.rclk)
        dut.rd_en.value = 0

    w = cocotb.start_soon(writer())
    r = cocotb.start_soon(reader())
    await w
    await r
    # After draining, the write side must see all reads (credit-return correctness)
    for _ in range(8):
        await RisingEdge(dut.wclk)
    assert int(dut.wr_rcount.value) == n % (2 * depth), "wr_rcount did not converge"
    assert int(dut.empty.value) == 1
    dut._log.info("fifo w=%dps r=%dps: %d words in order, max_occ=%d saw_full=%s",
                  wper, rper, n, state["max_occ"], state["saw_full"])


@cocotb.test()
async def fifo_random_clocks(dut):
    """Unrelated random clock periods drawn from the seed."""
    await fifo_traffic(dut, 2 * random.randint(500, 4500), 2 * random.randint(500, 4500))


@cocotb.test()
async def fifo_fast_write_slow_read(dut):
    await fifo_traffic(dut, 1014, 6998, n=1000, wr_bias=0.95, rd_bias=0.9)


@cocotb.test()
async def fifo_slow_write_fast_read(dut):
    await fifo_traffic(dut, 7918, 1010, n=1000, wr_bias=0.9, rd_bias=0.95)


def test_async_fifo():
    run("async_fifo", rtl("sync_2ff.sv", "async_fifo.sv"), "test_common",
        params={"W": 16, "DEPTH": 4},
        testcase="fifo_random_clocks,fifo_fast_write_slow_read,fifo_slow_write_fast_read")


def test_async_fifo_d16():
    run("async_fifo", rtl("sync_2ff.sv", "async_fifo.sv"), "test_common",
        params={"W": 80, "DEPTH": 16},
        testcase="fifo_random_clocks,fifo_fast_write_slow_read,fifo_slow_write_fast_read")


# --------------------------------------------------------------------------- credit_counter
@cocotb.test()
async def credit_random(dut):
    mx = int(dut.MAX.value)
    cocotb.start_soon(Clock(dut.clk, 1000, "ps").start())
    dut.consume.value = 0
    dut.ret.value = 0
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    model = mx
    outstanding = 0
    hit = set()
    for _ in range(5000):
        await FallingEdge(dut.clk)
        assert int(dut.count.value) == model
        assert int(dut.avail.value) == (model != 0)
        hit.add(model)
        c = 1 if (model > 0 and random.random() < 0.55) else 0
        r = random.randint(0, outstanding) if random.random() < 0.3 else 0
        dut.consume.value = c
        dut.ret.value = r
        model = model - c + r
        outstanding = outstanding + c - r
    assert hit == set(range(mx + 1)), f"not all credit levels visited: {sorted(hit)}"
    dut._log.info("credit_counter MAX=%d: 5000 cycles, levels %s", mx, sorted(hit))


def test_credit_counter():
    run("credit_counter", rtl("credit_counter.sv"), "test_common", params={"MAX": 4},
        testcase="credit_random")


# --------------------------------------------------------------------------- sync / reset
@cocotb.test()
async def sync_latency(dut):
    cocotb.start_soon(Clock(dut.clk, 1000, "ps").start())
    dut.rst_in_n.value = 0
    dut.d.value = 0
    await Timer(3500, "ps")
    await ReadOnly()
    assert int(dut.rst_out_n.value) == 0
    await FallingEdge(dut.clk)
    dut.rst_in_n.value = 1
    lat = 0
    while True:
        await RisingEdge(dut.clk)
        await ReadOnly()
        lat += 1
        if int(dut.rst_out_n.value):
            break
    assert lat == 2, f"reset deassert latency {lat}"
    await FallingEdge(dut.clk)
    dut.d.value = 1
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.q.value) == 0, "2FF must not pass d after 1 edge"
    await RisingEdge(dut.clk)
    await ReadOnly()
    assert int(dut.q.value) == 1, "2FF latency must be 2 edges"
    # asynchronous assertion: reset output drops without a clock edge
    await FallingEdge(dut.clk)
    dut.rst_in_n.value = 0
    await Timer(1, "ps")
    assert int(dut.rst_out_n.value) == 0


def test_sync():
    run("sync_wrap", rtl("sync_2ff.sv", "reset_sync.sv") + [str(HERE / "sync_wrap.sv")],
        "test_common", testcase="sync_latency")
