#!/usr/bin/env bash
# Containerized live-demo and runtime-replication driver.

set -euo pipefail
cd "$(dirname "$0")/.."

if docker compose version >/dev/null 2>&1; then
  COMPOSE_COMMAND=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE_COMMAND=(docker-compose)
else
  echo "Docker Compose v2 is required (docker compose or docker-compose)." >&2
  exit 1
fi
COMPOSE_BASE=("${COMPOSE_COMMAND[@]}" -f compose.yaml -f live-demo/compose.yaml)
COMPOSE=("${COMPOSE_BASE[@]}" --profile demo)
DSN="postgresql://postgres:postgres@postgres:5432/dblp"
FUSEKI_QUERY="http://fuseki:3030/dblp/query"
FUSEKI_DATA="http://fuseki:3030/dblp/data"
FUSEKI_PING='http://fuseki:3030/$/ping'
DATASET="config/dataset.full.json"
ACCEPTED_SUMMARY="results/final/summary.csv"
ACCEPTED_CAMPAIGN="results/final/campaign.json"
ACCEPTED_INSTANCES="config/instances.full.json"
EXPECTED_CPUS="${EXPECTED_CPUS:-10}"
EXPECTED_MEMORY_GIB="${EXPECTED_MEMORY_GIB:-8}"
DEMO_RUNTIME_LABEL="${DEMO_RUNTIME_LABEL:-$(docker context show)}"
export DEMO_RUNTIME_LABEL

usage() {
  local status="${1:-1}"
  cat <<'EOF'
Usage:
  live-demo/demo.sh prepare              build, start, verify, and load both stores
  live-demo/demo.sh ui                   start the presentation dashboard
  live-demo/demo.sh run --all            rerun all 13 accepted instances
  live-demo/demo.sh run Q1 Q5            rerun selected families
  live-demo/demo.sh run INSTANCE_ID      rerun selected frozen instances
  live-demo/demo.sh 1                    prepared-stack Q5 run and CSV comparison
  live-demo/demo.sh 2                    evidence-backed Q5 advisor output
  live-demo/demo.sh 3                    evidence-backed deep-Q3 advisor output
  live-demo/demo.sh all                  all three presentation beats
  live-demo/demo.sh down                 stop the Compose stack

The rigorous `run` command uses fresh service containers. Presentation beats
reuse the stack created by `prepare` and reload both stores before timing.
All evidence goes under live-demo/runs/; results/final/ is read-only.
EOF
  exit "$status"
}

pause() {
  echo
  read -r -p "── Press ENTER for the next beat ──"
  echo
}

tool() {
  "${COMPOSE[@]}" run --rm app "$@"
}

offline_tool() {
  "${COMPOSE[@]}" run --rm --no-deps app "$@"
}

run_quietly() {
  local log="$1"
  shift
  if ! "$@" >"$log" 2>&1; then
    cat "$log" >&2
    return 1
  fi
}

require_data() {
  local required=(
    data/canonical-full/metadata.json
    data/canonical-full/publication.csv
    data/canonical-full/person.csv
    data/canonical-full/authorship.csv
    data/rdf/dataset-full.nt
  )
  local path
  for path in "${required[@]}"; do
    [ -f "$path" ] || {
      echo "missing required full-scale artifact: $path" >&2
      exit 1
    }
  done
}

prepare() {
  local run_dir="$1"
  require_data
  echo "Recreating the Compose services for runtime: $DEMO_RUNTIME_LABEL"
  "${COMPOSE_BASE[@]}" down --remove-orphans
  "${COMPOSE[@]}" build app fuseki
  "${COMPOSE_BASE[@]}" up -d --wait postgres fuseki

  tool dm-demo environment \
    --dsn "$DSN" \
    --fuseki-ping "$FUSEKI_PING" \
    --runtime-label "$DEMO_RUNTIME_LABEL" \
    --expected-cpus "$EXPECTED_CPUS" \
    --expected-memory-gib "$EXPECTED_MEMORY_GIB" \
    --output "$run_dir/container-environment.json"

  tool dm-load-postgres \
    --dsn "$DSN" \
    --canonical data/canonical-full \
    --schema sql/schema.sql
  tool dm-load-fuseki data/rdf/dataset-full.nt \
    --graph-store-url "$FUSEKI_DATA"
}

record_runtime() {
  local host_dir="$1"
  docker context show > "$host_dir/docker-context.txt" 2> "$host_dir/docker-context.stderr.txt"
  docker version > "$host_dir/docker-version.txt" 2> "$host_dir/docker-version.stderr.txt"
  docker info > "$host_dir/docker-info.txt" 2> "$host_dir/docker-info.stderr.txt"
  "${COMPOSE_BASE[@]}" version > "$host_dir/compose-version.txt" 2> "$host_dir/compose-version.stderr.txt"
  "${COMPOSE_BASE[@]}" config > "$host_dir/compose-resolved.yaml" 2> "$host_dir/compose-config.stderr.txt"
  "${COMPOSE_BASE[@]}" images > "$host_dir/compose-images.txt" 2> "$host_dir/compose-images.stderr.txt"
}

check_competing_containers() {
  local allowed running container_id
  # The idle, read-only dashboard is part of the presentation stack. Any
  # container outside these three known services still invalidates the run.
  allowed="$("${COMPOSE_BASE[@]}" ps -q postgres fuseki ui)"
  running="$(docker ps --no-trunc -q)"
  while read -r container_id; do
    [ -z "$container_id" ] && continue
    grep -qx "$container_id" <<< "$allowed" || {
      echo "refusing to benchmark with a competing container: $container_id" >&2
      echo "stop unrelated containers or set up an isolated Docker runtime" >&2
      exit 1
    }
  done <<< "$running"
}

run_selected() {
  local lifecycle="$1"
  shift
  [ "$#" -ge 1 ] || usage
  local run_id="${DEMO_RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)-${DEMO_RUNTIME_LABEL//[^a-zA-Z0-9_-]/-}}"
  local host_dir="live-demo/runs/$run_id"
  local run_dir="/workspace/$host_dir"
  mkdir -p "$host_dir"

  if [ "$lifecycle" = "fresh" ]; then
    prepare "$run_dir"
  else
    require_data
    echo "Checking the prepared stack and restoring the canonical dataset..."
    run_quietly "$host_dir/compose-up.log" \
      "${COMPOSE_BASE[@]}" up -d --wait postgres fuseki
    run_quietly "$host_dir/environment.log" tool dm-demo environment \
      --dsn "$DSN" \
      --fuseki-ping "$FUSEKI_PING" \
      --runtime-label "$DEMO_RUNTIME_LABEL" \
      --expected-cpus "$EXPECTED_CPUS" \
      --expected-memory-gib "$EXPECTED_MEMORY_GIB" \
      --output "$run_dir/container-environment.json"
    # Reloading takes seconds and prevents a rehearsal or container restart
    # from leaving the staged demo in an unknown data state.
    run_quietly "$host_dir/postgres-load.log" tool dm-load-postgres \
      --dsn "$DSN" --canonical data/canonical-full --schema sql/schema.sql
    run_quietly "$host_dir/fuseki-load.log" tool dm-load-fuseki \
      data/rdf/dataset-full.nt --graph-store-url "$FUSEKI_DATA"
    echo "Prepared stack verified: 10 vCPUs, 8 GiB, both stores loaded."
  fi

  # Selection uses the containerized project CLI and preserves the accepted
  # instance objects byte-for-byte at the JSON-object level.
  run_quietly "$host_dir/selection.log" offline_tool dm-demo select \
    --source "$ACCEPTED_INSTANCES" \
    --output "$run_dir/instances.json" \
    -- "$@"

  record_runtime "$host_dir"
  check_competing_containers

  echo
  echo "Running the accepted 1 + 2 + 5 interleaved protocol."
  echo "Runtime: $DEMO_RUNTIME_LABEL"
  echo "Evidence: $host_dir"
  echo
  tool dm-benchmark \
    --dsn "$DSN" \
    --fuseki-endpoint "$FUSEKI_QUERY" \
    --dataset "$DATASET" \
    --instances "$run_dir/instances.json" \
    --query-dir queries \
    --output "$run_dir/benchmark.csv" \
    --progress-log "$run_dir/progress.jsonl" \
    --warmups 2 \
    --repetitions 5 \
    --timeout-seconds 300 \
    --execution-order interleaved \
    --scale full

  echo
  echo "Validating the run contract and comparing with accepted medians:"
  echo
  tool dm-demo compare \
    --live-benchmark "$run_dir/benchmark.csv" \
    --live-campaign "$run_dir/campaign.json" \
    --live-instances "$run_dir/instances.json" \
    --accepted-summary "$ACCEPTED_SUMMARY" \
    --accepted-campaign "$ACCEPTED_CAMPAIGN" \
    --accepted-instances "$ACCEPTED_INSTANCES" \
    --output "$run_dir/comparison.csv" \
    --metadata-output "$run_dir/comparison.json"

  cp "$host_dir/comparison.csv" live-demo/runs/latest-comparison.csv
  cp "$host_dir/comparison.json" live-demo/runs/latest-comparison.json

  echo
  echo "Runtime-replication evidence retained at: $host_dir"
}

beat2() {
  echo "═══ BEAT 2 · Q5: structural recommendation versus accepted evidence ═══"
  offline_tool dm-advisor Q5 --scale full --instance q5_ai_min2 \
    --summary "$ACCEPTED_SUMMARY" --dataset "$DATASET"
}

beat3() {
  echo "═══ BEAT 3 · Deep Q3: the same rule, much larger regret ═══"
  offline_tool dm-advisor Q3 --scale full --instance q3_pvldb_distance3_depth4 \
    --summary "$ACCEPTED_SUMMARY" --dataset "$DATASET"
}

case "${1:-}" in
  -h|--help)
    usage 0
    ;;
  prepare)
    run_id="${DEMO_RUN_ID:-prepare-$(date -u +%Y%m%dT%H%M%SZ)}"
    mkdir -p "live-demo/runs/$run_id"
    prepare "/workspace/live-demo/runs/$run_id"
    record_runtime "live-demo/runs/$run_id"
    echo "Prepared services; environment evidence: live-demo/runs/$run_id"
    ;;
  ui)
    "${COMPOSE[@]}" up -d --build ui
    echo "Presentation dashboard: http://localhost:8000"
    ;;
  run)
    shift
    run_selected fresh "$@"
    ;;
  1)
    run_selected prepared q5_ai_min2
    ;;
  2)
    beat2
    ;;
  3)
    beat3
    ;;
  all)
    run_selected prepared q5_ai_min2
    pause
    beat2
    pause
    beat3
    ;;
  down)
    "${COMPOSE_BASE[@]}" down --remove-orphans
    ;;
  *)
    usage
    ;;
esac
