"""Unit tests: replay_buffer, flit_tx, flit_rx, link_training_fsm."""
import random
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ReadOnly

from d2d_model import FT, ST, TRAIN_PATTERN, make_flit, split_flit
from runner import run, rtl


async def start(dut, sigs):
    cocotb.start_soon(Clock(dut.clk, 1000, "ps").start())
    for s, v in sigs.items():
        getattr(dut, s).value = v
    dut.rst_n.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1


# --------------------------------------------------------------------------- replay_buffer
@cocotb.test()
async def replay_buffer_random(dut):
    """Random enqueue / transmit / ACK / rewind against a Python Go-Back-N model."""
    depth = int(dut.DEPTH.value)
    await start(dut, dict(enq_valid=0, enq_body=0, rd_advance=0, ack_valid=0, ack_in=0, rewind=0))
    store = {}
    wr = rd = ack = 0
    stats = dict(enq=0, sent=0, rewinds=0, full=0)
    for cyc in range(6000):
        await FallingEdge(dut.clk)
        out = (wr - ack) & 0xFF
        assert int(dut.wr_seq.value) == wr and int(dut.rd_seq.value) == rd and int(dut.ack_seq.value) == ack
        assert int(dut.enq_ready.value) == (out < depth)
        assert int(dut.rd_valid.value) == (rd != wr)
        if rd != wr:
            assert int(dut.rd_body.value) == store[rd], f"body mismatch at seq {rd}"
        stats["full"] += out == depth
        # stimulus
        enq = random.random() < 0.5
        body = random.getrandbits(80)
        adv = random.random() < 0.6
        ackv = random.random() < 0.3
        # mostly legal ACKs (inside [ack, rd]) plus a few out-of-window ones
        if random.random() < 0.9:
            a = (ack + random.randint(0, (rd - ack) & 0xFF)) & 0xFF
        else:
            a = (wr + random.randint(1, 100)) & 0xFF
        rew = random.random() < 0.05
        dut.enq_valid.value = enq
        dut.enq_body.value = body
        dut.rd_advance.value = adv
        dut.ack_valid.value = ackv
        dut.ack_in.value = a
        dut.rewind.value = rew
        await ReadOnly()
        exp_moved = False
        # model next state
        do_enq = enq and out < depth
        do_adv = adv and rd != wr
        ack_ok = ackv and ((a - ack) & 0xFF) <= out
        ack_n = a if ack_ok else ack
        rd_adv = (rd + do_adv) & 0xFF
        rd_floor = ack_n if ((ack_n - ack) & 0xFF) > ((rd_adv - ack) & 0xFF) else rd_adv
        if rew:
            exp_moved = rd_floor != ack_n
            rd_n = ack_n
        else:
            rd_n = rd_floor
        assert int(dut.rewind_moved.value) == exp_moved
        assert int(dut.ack_ignored.value) == (ackv and not ack_ok)
        if do_enq:
            store[wr] = body
            stats["enq"] += 1
        stats["sent"] += do_adv
        stats["rewinds"] += exp_moved
        wr = (wr + do_enq) & 0xFF
        rd, ack = rd_n, ack_n
    assert stats["full"] > 0 and stats["rewinds"] > 0
    dut._log.info("replay_buffer DEPTH=%d: %s", depth, stats)


def test_replay_buffer():
    run("replay_buffer", rtl("replay_buffer.sv"), "test_link_blocks", params={"DEPTH": 4},
        testcase="replay_buffer_random")


def test_replay_buffer_d16():
    run("replay_buffer", rtl("replay_buffer.sv"), "test_link_blocks", params={"DEPTH": 16},
        testcase="replay_buffer_random")


# --------------------------------------------------------------------------- flit_tx / flit_rx
async def capture_flits(dut, sink, n):
    """Reassemble flits from the lane (independent of flit_rx)."""
    while len(sink) < n:
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.lane_valid.value) and int(dut.lane_sof.value):
            f = int(dut.lane_data.value)
            for _ in range(3):
                await RisingEdge(dut.clk)
                await ReadOnly()
                assert int(dut.lane_valid.value) and not int(dut.lane_sof.value)
                f = (f << 32) | int(dut.lane_data.value)
            sink.append(f)


@cocotb.test()
async def flit_loopback(dut):
    """flit_tx -> (fault XOR) -> flit_rx. Checks serialization, CRC, priorities and
    receiver sequence handling (accept / gap->NAK / duplicate drop)."""
    await start(dut, dict(send_en=0, train_mode=0, locked=0, nak_pending=0, rb_valid=0, rb_body=0,
                          rb_seq=0, ack_val=0, cred_req_cum=0, cred_rsp_cum=0, active=0,
                          fi_xor=0, req_full=0, rsp_full=0))
    # 1. TRAIN flits
    dut.send_en.value = 1
    dut.train_mode.value = 1
    dut.locked.value = 1
    flits = []
    await capture_flits(dut, flits, 3)
    for f in flits:
        d = split_flit(f)
        assert d["crc_ok"] and d["type"] == FT["TRAIN"] and d["payload"] == TRAIN_PATTERN and d["flags"] == 1
    # 2. ACTIVE: priority NAK > replay > ACK > CREDIT > IDLE
    await FallingEdge(dut.clk)
    dut.train_mode.value = 0
    dut.active.value = 1
    dut.ack_val.value = 7
    dut.cred_req_cum.value = 3
    flits = []
    await capture_flits(dut, flits, 4)  # first may be a TRAIN still in flight
    kinds = [split_flit(f)["type"] for f in flits]
    assert FT["ACK"] in kinds and kinds[-1] == FT["IDLE"], kinds
    # 3. drive sequenced flits from a model into the receiver via the replay port
    accepted = []
    naks = 0

    async def mon():
        nonlocal naks
        while True:
            await RisingEdge(dut.clk)
            await ReadOnly()
            if int(dut.push_req.value) or int(dut.push_rsp.value):
                accepted.append(int(dut.push_body.value))
            naks += int(dut.nak_req.value)

    cocotb.start_soon(mon())

    async def send_seq(seq, body, xor=0):
        await FallingEdge(dut.clk)
        dut.rb_valid.value = 1
        dut.rb_body.value = body
        dut.rb_seq.value = seq
        # rb_advance is combinational: the load happens on the edge that follows it
        while True:
            await ReadOnly()
            if int(dut.rb_advance.value):
                await RisingEdge(dut.clk)
                break
            await FallingEdge(dut.clk)
        await FallingEdge(dut.clk)
        dut.rb_valid.value = 0
        if xor:
            # corrupt beat 2 of the flit that is now being serialized
            for _ in range(2):
                await FallingEdge(dut.clk)
            dut.fi_xor.value = xor
            await FallingEdge(dut.clk)
            dut.fi_xor.value = 0
        for _ in range(12):
            await FallingEdge(dut.clk)

    bodies = [(FT["REQ_HDR"] << 76) | random.getrandbits(72) for _ in range(6)]
    await send_seq(0, bodies[0])
    await send_seq(1, bodies[1])
    assert accepted == bodies[:2]
    await send_seq(1, bodies[1])  # duplicate -> dropped silently
    assert accepted == bodies[:2] and naks == 0
    await send_seq(3, bodies[3])  # gap -> NAK, not accepted
    assert accepted == bodies[:2] and naks == 1
    await send_seq(2, bodies[2], xor=1 << 5)  # corrupted -> NAK suppressed (one outstanding)
    assert accepted == bodies[:2] and naks == 1
    await send_seq(2, bodies[2])  # good replay -> accepted, NAK re-armed
    await send_seq(4, bodies[4], xor=0xFFFF0000)  # corrupted -> new NAK
    assert accepted == bodies[:3] and naks == 2
    assert int(dut.exp_seq.value) == 3
    # NAK priority on the transmitter
    await FallingEdge(dut.clk)
    dut.nak_pending.value = 1
    flits = []
    await capture_flits(dut, flits, 2)
    await FallingEdge(dut.clk)
    dut.nak_pending.value = 0
    assert FT["NAK"] in [split_flit(f)["type"] for f in flits]
    dut._log.info("flit loopback: TRAIN/ACK/IDLE/NAK flits ok, accept/dup/gap/crc paths ok")


def test_flit_loopback():
    run("flit_loop_wrap", rtl("crc16.sv", "flit_tx.sv", "flit_rx.sv") +
        [str(Path(__file__).parent / "flit_loop_wrap.sv")], "test_link_blocks",
        testcase="flit_loopback")


# --------------------------------------------------------------------------- training FSM
async def pulse(dut, name, n=1):
    for _ in range(n):
        await FallingEdge(dut.clk)
        dut.flit_done.value = 1
        for s in ("bad", "train_good", "train_locked", "nontrain_good"):
            getattr(dut, s).value = 0
        for s in name.split("+"):
            if s:
                getattr(dut, s).value = 1
        await FallingEdge(dut.clk)
        for s in ("flit_done", "bad", "train_good", "train_locked", "nontrain_good"):
            getattr(dut, s).value = 0


async def wait_state(dut, st, limit=5000):
    for _ in range(limit):
        await RisingEdge(dut.clk)
        await ReadOnly()
        if int(dut.state.value) == st:
            return
    raise AssertionError(f"state {st} not reached, at {int(dut.state.value)}")


@cocotb.test()
async def ltssm_directed(dut):
    await start(dut, dict(enable=1, force_retrain=0, err_thresh=2, max_retrain=2, err_window=16,
                          flit_done=0, bad=0, train_good=0, train_locked=0, nontrain_good=0))
    await wait_state(dut, ST["TRAIN"])
    # 3 good, 1 bad resets lock count, then 4 good with remote locked
    await pulse(dut, "train_good", 3)
    await pulse(dut, "bad")
    await pulse(dut, "train_good", 3)
    assert int(dut.state.value) == ST["TRAIN"]
    await pulse(dut, "train_good+train_locked")
    await wait_state(dut, ST["ACTIVE"], 4)
    # peer finishing training (TRAIN with LOCKED=1) must be ignored in ACTIVE
    await pulse(dut, "train_good+train_locked", 3)
    assert int(dut.state.value) == ST["ACTIVE"]
    # error burst above threshold -> RETRAIN
    await pulse(dut, "bad", 3)
    await wait_state(dut, ST["RETRAIN"], 4)
    await pulse(dut, "train_good", 4)
    await pulse(dut, "nontrain_good")  # peer already active counts as remote ready
    await wait_state(dut, ST["ACTIVE"], 4)
    # peer-initiated retrain (TRAIN, LOCKED=0)
    await pulse(dut, "train_good")
    await wait_state(dut, ST["RETRAIN"], 4)
    # no lock -> training timeouts exhaust attempts -> FAILED
    await wait_state(dut, ST["FAILED"], 4 * 600)
    await FallingEdge(dut.clk)
    dut.enable.value = 0
    await wait_state(dut, ST["RESET"], 4)
    await FallingEdge(dut.clk)
    dut.enable.value = 1
    await wait_state(dut, ST["TRAIN"], 4)
    await pulse(dut, "train_good+train_locked", 4)
    await wait_state(dut, ST["ACTIVE"], 4)
    await FallingEdge(dut.clk)
    dut.force_retrain.value = 1
    await FallingEdge(dut.clk)
    dut.force_retrain.value = 0
    await wait_state(dut, ST["RETRAIN"], 4)
    dut._log.info("ltssm: all transitions exercised")


def test_ltssm():
    run("link_training_fsm", rtl("link_training_fsm.sv"), "test_link_blocks",
        params={"TRAIN_GOOD": 4, "TRAIN_TIMEOUT": 256, "STABLE_CYCLES": 512}, testcase="ltssm_directed")
