"""Shared cocotb/Verilator runner for unit tests (run with pytest inside the container)."""
import os
import hashlib
from pathlib import Path

from cocotb.runner import get_runner

ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "rtl"


def rtl(*names):
    """Resolve RTL file names (searched in rtl/ and rtl/common/)."""
    out = []
    for n in names:
        p = RTL / n
        if not p.exists():
            p = RTL / "common" / n
        assert p.exists(), n
        out.append(str(p))
    return out


def run(toplevel, sources, test_module, params=None, seed=None, extra_env=None, testcase=None):
    params = params or {}
    tag = hashlib.md5(repr(sorted(params.items())).encode()).hexdigest()[:6]
    # Build outside the bind mount: much faster than building on the Windows share.
    build_dir = Path(os.environ.get("SIM_BUILD_ROOT", "/tmp/sim_build")) / f"{toplevel}_{tag}"
    runner = get_runner("verilator")
    runner.build(
        verilog_sources=sources,
        hdl_toplevel=toplevel,
        includes=[str(RTL)],
        defines={"SIM": 1},
        parameters=params,
        build_args=["--assert", "-Wno-fatal", "-Wno-WIDTH", "-Wno-UNUSED", "-O2"],
        build_dir=str(build_dir),
    )
    env = dict(extra_env or {})
    seed = seed if seed is not None else os.environ.get("SEED")
    runner.test(
        hdl_toplevel=toplevel,
        test_module=test_module,
        build_dir=str(build_dir),
        test_dir=str(Path(__file__).parent),
        seed=seed,
        testcase=testcase.split(",") if testcase else None,
        extra_env=env,
    )
