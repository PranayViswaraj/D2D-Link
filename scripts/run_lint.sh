#!/usr/bin/env bash
# Lint: Verilator -Wall (full design, synthesis view) and Verible style lint.
# Logs: logs/lint_verilator.log, logs/lint_verible.log. Exit non-zero on any warning.
set -u
cd "$(dirname "$0")/.."
rc=0
verilator --lint-only -Wall -Irtl -f rtl/files.f --top-module d2d_system_top > logs/lint_verilator.log 2>&1 || rc=1
verilator --lint-only -Wall -Irtl -DSIM -f rtl/files.f --top-module d2d_system_top >> logs/lint_verilator.log 2>&1 || rc=1
verible-verilog-lint --rules_config .rules.verible_lint $(cat rtl/files.f) > logs/lint_verible.log 2>&1 || rc=1
echo "verilator warnings: $(grep -c '^%Warning' logs/lint_verilator.log)"
echo "verible violations: $(grep -c 'Style:' logs/lint_verible.log)"
exit $rc
