"""Build d2d_system_top once per configuration and run one pyuvm test.

usage: python tb/uvm/run_test.py --test random_rw --seed 1 [--config default|small] [--build-only]
"""
import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from cocotb.runner import get_runner  # noqa: E402

CONFIGS = {
    "default": {},
    "small": dict(REPLAY_DEPTH=4, CREDITS_REQ=4, CREDITS_RSP=4, TX_FIFO_DEPTH=4,
                  REPLAY_TIMEOUT=128, TRAIN_GOOD=4, TRAIN_TIMEOUT=512, STABLE_CYCLES=1024),
}


def build(config):
    files = [str(ROOT / l.strip()) for l in open(ROOT / "rtl" / "files.f") if l.strip()]
    bdir = Path(os.environ.get("SIM_BUILD_ROOT", "/tmp/sim_build")) / f"system_{config}"
    r = get_runner("verilator")
    r.build(verilog_sources=files, hdl_toplevel="d2d_system_top", includes=[str(ROOT / "rtl")],
            defines={"SIM": 1}, parameters=CONFIGS[config],
            build_args=["--assert", "-Wno-fatal", "-O2", "--x-assign", "unique", "--x-initial", "unique"],
            build_dir=str(bdir))
    return r, bdir


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default="smoke")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--config", default="default", choices=CONFIGS)
    ap.add_argument("--build-only", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "logs" / "regress"))
    a = ap.parse_args()
    r, bdir = build(a.config)
    if a.build_only:
        return
    seed = a.seed if a.seed is not None else int.from_bytes(os.urandom(3), "little")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = f"{a.test}_{a.config}_{seed}"
    r.test(hdl_toplevel="d2d_system_top", test_module="d2d_tests", testcase=a.test,
           build_dir=str(bdir), test_dir=str(HERE), seed=seed,
           extra_env={"D2D_RESULT_DIR": str(out / a.config), "PYTHONPATH": str(HERE),
                      "PYTHONUNBUFFERED": "1"},
           results_xml=str(out / f"{tag}.xml"))


if __name__ == "__main__":
    main()
