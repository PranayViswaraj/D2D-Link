# Lint Waivers

`scripts/run_lint.sh` runs Verilator `--lint-only -Wall` on `d2d_system_top`, both in the synthesis
view and with `-DSIM` (embedded assertions enabled), and Verible lint on every RTL file. The current
result is **0 Verilator warnings and 0 Verible violations** (`logs/lint_verilator.log`,
`logs/lint_verible.log`). The waivers that make this possible are listed below. Each one is local and
named in the code.

## Verilator

| File | Waiver | Justification |
|------|--------|---------------|
| `rtl/d2d_defs.svh` | `lint_off UNUSEDPARAM` around the shared constants | Header included by many modules; each uses a subset of the flit/state constants |
| `rtl/apb_csr.sv` | `unused_ok` sink for `pwdata[31:16]` | All registers are at most 16 bits wide |
| `rtl/axi_slave_adapter.sv` | sink for `awlen[7:4]`, `arlen[7:4]`, `wlast`, reserved RSP bits | AxLEN is limited to 16 beats (spec 5.3, asserted in SIM). WLAST is regenerated from the beat counter and is checked against the host's WLAST by an assertion |
| `rtl/axi_master_adapter.sv` | sink for `req_rdata[79:72]` | Flit type/flags at Die B are only checked by assertions; WLAST comes from the beat counter |
| `rtl/common/credit_counter.sv` | sink for `next9[8:5]` | Upper bits exist only to detect overflow in the bound assertion |
| `rtl/link_layer.sv` | sink for `cq_count`, `cs_count`, `wr_seq`, `ack_ptr`, `ack_ignored` | Kept for debug visibility (probed by the testbench); `ack_ignored` feeds an assertion |

## Verible (`.rules.verible_lint`)

| Rule | Action | Justification |
|------|--------|---------------|
| `parameter-name-style` | `localparam_style:ALL_CAPS` | Project convention: localparams are ALL_CAPS (`FT_REQ_HDR`, `ST_ACTIVE`); Verible's default is CamelCase |
| `unpacked-dimensions-range-ordering` | inline waiver on the two memory arrays | `[0:DEPTH-1]` is kept because it is the form Yosys 0.33's native parser is known to accept |
