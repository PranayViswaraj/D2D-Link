#!/usr/bin/env bash
# Run all SymbiYosys jobs (small configuration); each task is capped at 5 minutes.
# Logs: formal/<job>_<task>/logfile.txt ; summary: logs/formal_summary.txt
set -u
cd "$(dirname "$0")/../formal"
: > ../logs/formal_summary.txt
rc=0
for job in fifo credit replay retry ltssm; do
  start=$(date +%s)
  timeout 300 sby -f "${job}.sby" > "../logs/formal_${job}.log" 2>&1 || rc=1
  end=$(date +%s)
  grep -hE "DONE \(|summary:.*(PASS|FAIL)|Status: (passed|failed)" ${job}_*/logfile.txt 2>/dev/null \
    | sed "s/^/${job}: /" >> ../logs/formal_summary.txt
  echo "${job}: wall $((end - start)) s" >> ../logs/formal_summary.txt
done
cat ../logs/formal_summary.txt
exit $rc
