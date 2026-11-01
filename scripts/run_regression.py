#!/usr/bin/env python3
"""Parallel regression for D2D-Link system tests (run inside the d2d-eda container).

Runs every (test, seed, config) job on all CPU cores, enforces a global wall-clock cap,
and writes:
  logs/regress/junit.xml        merged JUnit XML
  logs/regress/summary.md       pass/fail table with seeds, transactions and faults
  logs/regress/<cfg>/*.json     per-run results + coverage (consumed by scripts/report.py)

usage: scripts/run_regression.py [--seeds N] [--configs default,small] [--tests a,b] [--cap-min 15]
"""
import argparse
import glob
import json
import os
import random
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "logs" / "regress"
TESTS = ["smoke", "random_rw", "max_burst", "outstanding_stress", "credit_starvation",
         "backpressure_random", "crc_error_retry", "flit_drop_timeout", "error_storm_retrain",
         "link_fail_and_recover", "csr_access", "ltssm_arcs", "clock_ratio_sweep", "reset_during_traffic"]
# the small config is exercised by a fast subset (it is also the formal config)
SMALL_TESTS = ["smoke", "random_rw", "max_burst", "credit_starvation", "crc_error_retry",
               "flit_drop_timeout", "error_storm_retrain", "reset_during_traffic"]


def run_job(test, seed, cfg, deadline):
    tag = f"{test}_{cfg}_{seed}"
    log = OUT / "logs" / f"{tag}.log"
    remaining = max(30, int(deadline - time.time()))
    t0 = time.time()
    cmd = [sys.executable, str(ROOT / "tb/uvm/run_test.py"), "--test", test, "--seed", str(seed),
           "--config", cfg, "--out", str(OUT)]
    try:
        with open(log, "w") as f:
            subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, timeout=min(remaining, 600))
        status = "timeout?"
    except subprocess.TimeoutExpired:
        status = "TIMEOUT"
    xmlf = OUT / f"{tag}.xml"
    if xmlf.exists():
        tree = ET.parse(xmlf)
        tcs = tree.findall(".//testcase")
        failed = any(tc.find("failure") is not None or tc.find("error") is not None for tc in tcs)
        status = "FAIL" if failed or not tcs else "PASS"
    elif status != "TIMEOUT":
        status = "ERROR"
    res = {}
    rj = OUT / cfg / f"{test}_{seed}.json"
    if rj.exists():
        res = json.loads(rj.read_text())
    return dict(test=test, seed=seed, cfg=cfg, status=status, secs=round(time.time() - t0, 1),
                log=str(log.relative_to(ROOT)), **{k: res.get(k) for k in
                ("transactions", "faults_total", "counters_a", "counters_b")})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--configs", default="default,small")
    ap.add_argument("--tests", default=None)
    ap.add_argument("--cap-min", type=float, default=15.0)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    ap.add_argument("--base-seed", type=int, default=None)
    a = ap.parse_args()

    t_start = time.time()
    deadline = t_start + 60 * a.cap_min
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    for old in glob.glob(str(OUT / "*.xml")) + glob.glob(str(OUT / "*" / "*.json")) + \
            glob.glob(str(OUT / "*" / "cov" / "*.json")):
        os.remove(old)
    base = a.base_seed if a.base_seed is not None else random.randrange(1, 1 << 20)
    print(f"regression base seed {base}, cap {a.cap_min} min, {a.jobs} jobs", flush=True)

    configs = a.configs.split(",")
    for cfg in configs:  # build each configuration once, sequentially
        subprocess.run([sys.executable, str(ROOT / "tb/uvm/run_test.py"), "--config", cfg,
                        "--build-only"], check=True, stdout=subprocess.DEVNULL)
    jobs = []
    for cfg in configs:
        tests = a.tests.split(",") if a.tests else (TESTS if cfg == "default" else SMALL_TESTS)
        for i in range(a.seeds):
            for t in tests:
                jobs.append((t, base + 1000 * i + len(jobs), cfg))
    results = []
    with ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = {}
        for j in jobs:
            futs[ex.submit(lambda j=j: run_job(*j, deadline) if time.time() < deadline else
                           dict(test=j[0], seed=j[1], cfg=j[2], status="SKIPPED(cap)", secs=0, log=""))] = j
        for fu in as_completed(futs):
            r = fu.result()
            results.append(r)
            print(f"[{len(results):3d}/{len(jobs)}] {r['status']:8s} {r['cfg']:7s} {r['test']:22s} "
                  f"seed={r['seed']} {r['secs']}s", flush=True)
    wall = time.time() - t_start

    # merged JUnit
    suite = ET.Element("testsuite", name="d2d_regression", tests=str(len(results)),
                       failures=str(sum(r["status"] != "PASS" for r in results)), time=f"{wall:.1f}")
    for r in sorted(results, key=lambda r: (r["cfg"], r["test"], r["seed"])):
        tc = ET.SubElement(suite, "testcase", classname=f"d2d.{r['cfg']}", name=f"{r['test']}[seed={r['seed']}]",
                           time=str(r["secs"]))
        if r["status"] != "PASS":
            ET.SubElement(tc, "failure", message=r["status"]).text = r["log"]
    ET.ElementTree(suite).write(OUT / "junit.xml")

    npass = sum(r["status"] == "PASS" for r in results)
    lines = [f"# Regression summary", "",
             f"- base seed: {base}", f"- jobs: {len(results)}, passed: {npass}, failed: {len(results) - npass}",
             f"- wall clock: {wall / 60:.1f} min (cap {a.cap_min} min, {a.jobs} parallel jobs)",
             f"- transactions checked: {sum(r.get('transactions') or 0 for r in results)}",
             f"- faulted flits injected: {sum(r.get('faults_total') or 0 for r in results)}", "",
             "| config | test | seed | status | time (s) | txns | faults | A: crc/nak/replay/tmo/retrain | B: crc/nak/replay/tmo/retrain |",
             "|---|---|---|---|---|---|---|---|---|"]
    fmt = lambda c: "/".join(str(c[k]) for k in ("crc_err_cnt", "nak_cnt", "replay_cnt", "timeout_cnt",
                                                  "retrain_cnt")) if c else "-"
    for r in sorted(results, key=lambda r: (r["cfg"], r["test"], r["seed"])):
        lines.append(f"| {r['cfg']} | {r['test']} | {r['seed']} | {r['status']} | {r['secs']} | "
                     f"{r.get('transactions') or '-'} | {r.get('faults_total') or 0} | {fmt(r.get('counters_a'))} | "
                     f"{fmt(r.get('counters_b'))} |")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:7]))
    sys.exit(0 if npass == len(results) else 1)


if __name__ == "__main__":
    main()
