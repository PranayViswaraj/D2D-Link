#!/usr/bin/env bash
# Yosys synthesis of each major block (default parameters) and of both die tops.
#  - generic:  synth + abc (internal gate library) -> cell counts
#  - mapped:   dfflibmap + abc -liberty SKY130 HD tt_025C_1v80 -> area (um^2) and
#              ABC 'stime' critical combinational path delay (an ESTIMATE: no wires,
#              no clock tree, no OpenSTA). Skipped if the liberty file is missing.
# Reports: syn/reports/<block>.log, summary: syn/reports/summary.txt
set -u
cd "$(dirname "$0")/.."
LIB=syn/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
LIB_URL=https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
mkdir -p syn/reports syn/lib
[ -f "$LIB" ] || curl -fsSL --max-time 900 -o "$LIB" "$LIB_URL" || rm -f "$LIB"
FILES=$(tr '\n' ' ' < rtl/files.f)
: > syn/reports/summary.txt

# block | parameter overrides (Yosys chparam syntax)
BLOCKS="async_fifo:-set_W_80_-set_DEPTH_16
crc16:
replay_buffer:
flit_tx:
flit_rx:
link_training_fsm:
link_layer:
axi_slave_adapter:
axi_master_adapter:
apb_csr:
die_a_top:
die_b_top:"

for entry in $BLOCKS; do
  top=${entry%%:*}
  params=$(echo "${entry#*:}" | tr '_' ' ')
  chp=""
  [ -n "$params" ] && chp="chparam $params $top;"
  if [ -f "$LIB" ]; then
    map="dfflibmap -liberty $LIB; abc -liberty $LIB -script +strash;dch,-f;map;topo;stime,-p; opt_clean; stat -liberty $LIB"
  else
    map="abc; opt_clean; stat"
  fi
  timeout 600 yosys -q -l "syn/reports/${top}.log" -p "read_verilog -sv -Irtl $FILES; $chp synth -flatten -top $top; select -assert-none t:\$dlatch; tee -o syn/reports/${top}_generic.txt stat; $map; tee -o syn/reports/${top}_mapped.txt stat $( [ -f "$LIB" ] && echo "-liberty $LIB")" \
      > /dev/null 2>&1 || echo "$top: SYNTH FAILED" >> syn/reports/summary.txt
  cells=$(grep -m1 "Number of cells:" "syn/reports/${top}_generic.txt" | awk '{print $4}')
  area=$(grep -m1 "Chip area" "syn/reports/${top}_mapped.txt" 2>/dev/null | awk '{print $NF}')
  ffs=$(grep -E "_DFF|dfxtp|dfrtp" "syn/reports/${top}_mapped.txt" 2>/dev/null | awk '{s+=$2} END {print s+0}')
  delay=$(grep -oE "Delay = +[0-9.]+ ps" "syn/reports/${top}.log" | tail -1 | grep -oE "[0-9.]+")
  printf "%-20s generic_cells=%-6s sky130_area_um2=%-12s flops=%-6s abc_comb_delay_ps=%s\n" \
      "$top" "${cells:-?}" "${area:-n/a}" "${ffs:-?}" "${delay:-n/a}" >> syn/reports/summary.txt
done
cat syn/reports/summary.txt
