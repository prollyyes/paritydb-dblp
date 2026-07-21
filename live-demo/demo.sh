#!/usr/bin/env bash
# Live demo driver for the ParityDB-DBLP presentation.
#
# Presentation beats:
#   ./demo.sh 1                beat 1: live paired run of q5_ai_min2 (correctness gate + timings)
#   ./demo.sh 2                beat 2: advisor on Q5 (recommendation vs measured evidence)
#   ./demo.sh 3                beat 3: advisor on deep Q3 (same policy, 100+ s regret)
#   ./demo.sh all              all three beats, pausing for ENTER between them
#
# Live re-execution of the benchmark (see README for measured durations):
#   ./demo.sh run --all        every instance (~40 min at 100% CPU)
#   ./demo.sh run Q1 Q5        one or more query families
#   ./demo.sh run q3_direct_depth2   one or more single instances
#
# After a run, the live medians are compared against the accepted campaign
# (results/final/summary.csv) and winner flips are flagged.
#
# Requires the two services running with data loaded (docker compose up,
# dm-load-postgres, dm-load-fuseki). Terminal output only: the benchmark
# runner needs a working file, so it writes into a temporary directory that
# is removed when the script exits. Nothing in the repository is touched.

set -euo pipefail
cd "$(dirname "$0")/.."

VENV=".venv/bin"
SUMMARY="results/final/summary.csv"
DATASET="config/dataset.full.json"
OUT_DIR="$(mktemp -d -t paritydb-demo)"
trap 'rm -rf "$OUT_DIR"' EXIT

# The Postgres container maps container port 5432 to a host port that differs
# between machines; resolve it from docker instead of hardcoding.
PG_PORT="${PG_PORT:-$(docker compose port postgres 5432 2>/dev/null | cut -d: -f2)}"
PG_PORT="${PG_PORT:-5432}"
DSN="${DSN:-postgresql://postgres:postgres@localhost:${PG_PORT}/dblp}"
FUSEKI="${FUSEKI:-http://localhost:3030/dblp/query}"

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 1
}

pause() { echo; read -r -p "── ENTER per il beat successivo ──"; echo; }

print_targets() {
  echo "postgres:  $DSN"
  echo "fuseki:    $FUSEKI"
  echo "protocol:  1 correctness run + 2 warm-ups + 5 measured per backend, interleaved order"
  echo "gate:      identical row_count and SHA-256 result hash required before any timing"
}

# Approximate wall-clock seconds per instance on the demo machine
# (M2 Pro, Docker Desktop, full scale — measured 2026-07-21).
est_seconds() {
  case "$1" in
    q1_all_decades)            echo 4 ;;
    q1_db_yearly)              echo 2 ;;
    q1_ai_yearly)              echo 2 ;;
    q2_db_min3)                echo 610 ;;
    q2_db_min5)                echo 310 ;;
    q3_direct_depth2)          echo 185 ;;
    q3_pvldb_distance3_depth2) echo 3 ;;
    q3_pvldb_distance3_depth4) echo 565 ;;
    q3_pvldb_out_of_reach)     echo 565 ;;
    q4_moderate_min1)          echo 90 ;;
    q4_moderate_min2)          echo 85 ;;
    q5_dm_min1)                echo 9 ;;
    q5_ai_min2)                echo 9 ;;
    *)                         echo 60 ;;
  esac
}

beat1() {
  echo "═══ BEAT 1 · Live paired run: q5_ai_min2 (correctness gate, then timings) ═══"
  print_targets
  echo
  "$VENV/dm-benchmark" \
    --dsn "$DSN" \
    --fuseki-endpoint "$FUSEKI" \
    --dataset "$DATASET" \
    --instances live-demo/instances.demo.json \
    --query-dir queries \
    --output "$OUT_DIR/demo-benchmark.csv" \
    --warmups 2 \
    --repetitions 5 \
    --scale full \
    --execution-order interleaved
  echo
  echo "16 executions recorded. Check the row_count and result_sha256 columns:"
  echo "every run on both backends must show the same values."
  echo
  column -s, -t "$OUT_DIR/demo-benchmark.csv"
}

beat2() {
  echo "═══ BEAT 2 · Advisor on Q5: recommendation vs correctness-gated evidence ═══"
  echo "reads:     $SUMMARY (committed campaign evidence; services not used)"
  echo
  echo "\$ dm-advisor Q5 --scale full --instance q5_ai_min2"
  "$VENV/dm-advisor" Q5 --scale full --instance q5_ai_min2 \
    --summary "$SUMMARY" --dataset "$DATASET"
}

beat3() {
  echo "═══ BEAT 3 · Same policy on deep Q3: the regret becomes 100+ seconds ═══"
  echo "reads:     $SUMMARY (committed campaign evidence; services not used)"
  echo
  echo "\$ dm-advisor Q3 --scale full --instance q3_pvldb_distance3_depth4"
  "$VENV/dm-advisor" Q3 --scale full --instance q3_pvldb_distance3_depth4 \
    --summary "$SUMMARY" --dataset "$DATASET"
}

run_selected() {
  [ $# -ge 1 ] || usage

  local ids
  ids=$("$VENV/python" - "$OUT_DIR" "$@" <<'PY'
import json
import sys

out_dir = sys.argv[1]
tokens = sys.argv[2:]
data = json.load(open("config/instances.full.json"))["instances"]
known_ids = {i["id"] for i in data}
families = {"Q1", "Q2", "Q3", "Q4", "Q5"}

if tokens == ["--all"]:
    selected = list(data)
else:
    selected = []
    for token in tokens:
        if token.upper() in families:
            selected += [i for i in data if i["profile"] == token.upper()]
        elif token in known_ids:
            selected += [i for i in data if i["id"] == token]
        else:
            sys.exit(f"unknown family or instance: {token!r} "
                     f"(families: Q1-Q5; instance ids are in config/instances.full.json)")

seen, ordered = set(), []
for inst in selected:
    if inst["id"] not in seen:
        seen.add(inst["id"])
        ordered.append(inst)

with open(f"{out_dir}/instances.selected.json", "w") as fh:
    json.dump({"instances": ordered}, fh, indent=2)
print(" ".join(inst["id"] for inst in ordered))
PY
  )

  local total=0 n=0 inst
  for inst in $ids; do
    total=$((total + $(est_seconds "$inst")))
    n=$((n + 1))
  done

  echo "═══ Live benchmark re-execution ═══"
  print_targets
  echo "instances: $n selected -> $ids"
  echo "scratch:   temporary directory, removed on exit (terminal output only)"
  printf 'estimate:  ~%d min on this machine (CPU near 100%% for the whole time)\n' $(( (total + 59) / 60 ))
  echo

  "$VENV/dm-benchmark" \
    --dsn "$DSN" \
    --fuseki-endpoint "$FUSEKI" \
    --dataset "$DATASET" \
    --instances "$OUT_DIR/instances.selected.json" \
    --query-dir queries \
    --output "$OUT_DIR/live-benchmark.csv" \
    --warmups 2 \
    --repetitions 5 \
    --timeout-seconds 300 \
    --execution-order interleaved \
    --scale full

  echo
  echo "Comparing live medians against the accepted campaign ($SUMMARY):"
  echo
  "$VENV/python" live-demo/compare.py "$OUT_DIR/live-benchmark.csv" "$SUMMARY"
}

case "${1:-}" in
  1) beat1 ;;
  2) beat2 ;;
  3) beat3 ;;
  all) beat1; pause; beat2; pause; beat3 ;;
  run) shift; run_selected "$@" ;;
  *) usage ;;
esac
