# Containerized live demo and runtime replication

The live demo runs the project tooling in Docker and orchestrates PostgreSQL,
Fuseki, fresh data loads, the benchmark, and the comparison through Docker
Compose. The host needs only Docker with the Compose plugin and the previously
generated full-scale data under `data/`.

The accepted campaign under `results/final/` is immutable reference evidence.
Every live run is a **runtime replication** stored under the ignored directory
`live-demo/runs/`; it never overwrites or replaces the accepted campaign.

## Why runtime provenance matters

The accepted campaign used a Colima VM with 10 vCPUs and 8 GiB. A later run
under Docker Desktop produced different absolute timings and four mechanical
median-winner flips. Equal advertised CPU and memory do not make the
environments identical: the Docker engine, Linux VM, virtualization and
networking path, scheduler state, and service lifecycle may still differ.

The observed difference is therefore **associated with a runtime change**, not
causally attributed to Colima or Docker Desktop alone. The demo records the
Docker context, engine information, resolved Compose configuration, image
identities, container-visible CPU/RAM, PostgreSQL version, and Fuseki health
with every rerun so the difference remains auditable.

There is also an intentional client-placement difference: the accepted runner
executed on macOS and reached published host ports, whereas the containerized
demo runner reaches both services on the private Compose network. This removes
host-language setup from the demo but means a live timing is a replication,
not a byte-for-byte recreation of the accepted timing path.

## Commands

Run from the repository root:

```bash
live-demo/demo.sh prepare              # fresh services + full data load
live-demo/demo.sh ui                   # dashboard at http://localhost:8000
live-demo/demo.sh run --all            # all 13 accepted instances
live-demo/demo.sh run Q1               # one family
live-demo/demo.sh run Q1 Q5            # several families
live-demo/demo.sh run q3_direct_depth2 # one frozen instance

live-demo/demo.sh 1                    # presentation beat 1: live Q5 rerun
live-demo/demo.sh 2                    # presentation beat 2: Q5 advisor replay
live-demo/demo.sh 3                    # presentation beat 3: deep-Q3 advisor replay
live-demo/demo.sh all                  # all presentation beats
live-demo/demo.sh down                 # stop the stack
```

`run` always recreates both backend containers and reloads both stores before
timing. Families and instances may be mixed; duplicates are removed while the
accepted instance order is preserved. Unknown names fail before the benchmark.
The script also refuses to start timing if any container outside the two fresh
backend services is running.

For the presentation, execute `prepare` before entering the room. Beats `1`
and `all` then reuse those healthy containers, reload both stores to eliminate
unknown rehearsal state, and run only `q5_ai_min2`. They do not rebuild images
or recreate the VM on stage.

The expected VM allocation defaults to 10 CPUs and 8 GiB. Override only when
deliberately testing another environment:

```bash
EXPECTED_CPUS=8 EXPECTED_MEMORY_GIB=12 live-demo/demo.sh run Q1
```

That override makes the run executable; it does not make its timings directly
equivalent to the accepted campaign.

## What Compose owns

`compose.yaml` defines three services:

- `postgres`: PostgreSQL 17.10 with a readiness healthcheck;
- `fuseki`: Fuseki 6.1.0 in memory with a readiness healthcheck;
- `app`: the project CLI in a Python 3.12 image built from `Dockerfile.app`.

`live-demo/compose.yaml` removes the two host port publications for demo runs.
The app reaches both databases by service name on the private Compose network,
so an unrelated local PostgreSQL or Fuseki process cannot cause a port clash.

The app container receives the repository's `data/` directory read-only and
may write only to `live-demo/runs/`. Extraction is intentionally not part of a
presentation run: the pinned multi-gigabyte DBLP source takes hours to process,
whereas the already verified canonical full extract is the accepted data
boundary. The loaders, benchmark, advisor, selection, preflight, and comparison
all run inside the app image.

## Comparison safety gate

`dm-demo compare` refuses to compare live timings unless all of the following
match the accepted campaign:

- successful campaign status;
- scale and dataset SHA-256;
- timeout, warm-up count, measured repetition count, and execution order;
- exact instance objects for every selected id;
- one first run, two warm-ups, and five measured runs per backend;
- successful execution of every row;
- one stable row-count/result-hash signature per instance;
- accepted summary rows from the same dataset with five measured runs.

Only after those checks does it write median ratios and winner flips. The
result is explicitly labeled `comparable_runtime_replication`, with
`authoritative_campaign_replaced: false`.

## Evidence bundle

Each run creates a timestamped directory containing:

```text
benchmark.csv              raw live executions
summary.csv                live medians/min/max from dm-benchmark
campaign.json              live protocol and configuration fingerprints
instances.json             exact selected accepted instances
progress.jsonl             untimed UTC progress events
comparison.csv             live versus accepted medians and ratios
comparison.json            comparison acceptance and flip count
container-environment.json container-visible resources and service versions
docker-context.txt         selected Docker context
docker-version.txt         client/server versions
docker-info.txt            runtime and VM-facing engine information
compose-version.txt        Compose version
compose-resolved.yaml      fully resolved orchestration configuration
compose-images.txt         service image identities
```

These artifacts are local by default and should not be mixed into
`results/final/`.

## Presentation plan

The safe sequence is:

```bash
# Before the presentation
live-demo/demo.sh prepare
live-demo/demo.sh ui

# On stage
live-demo/demo.sh all
```

Keep the dashboard open at `http://localhost:8000`. It visualizes the accepted
campaign and polls `live-demo/runs/latest-comparison.csv` when you press
**Refresh live result**. The dashboard is intentionally read-only: benchmark
execution remains in the auditable CLI, so an accidental browser click cannot
start a long campaign or alter accepted evidence.

The isolation guard permits the project dashboard during the presentation
replication but still rejects every unrelated container. The accepted campaign,
not this staged replication, remains the authoritative isolated measurement.

The staged sequence normally finishes well within ten minutes. If `prepare`
has not succeeded, do not improvise a build on stage: use beats `2` and `3`,
which replay committed accepted evidence and require no running services.

Beat 1 reruns `q5_ai_min2` with the accepted 1 + 2 + 5 protocol, validates the
result signatures, and compares live medians with the accepted CSV. Say before
running it:

> This is a controlled runtime replication, not a replacement campaign. The
> answers must remain identical; absolute timings and close-race winners may
> change with the container runtime.

Beat 2 replays the accepted Q5 evidence through the advisor. Point out that the
structural rule recommends Fuseki, while the accepted measured winner is
PostgreSQL with 535.070 ms regret.

Beat 3 replays the deep-Q3 case without executing its roughly two-minute
accepted Fuseki query. It shows 101,728.196 ms regret and returns to the main
finding: query shape alone was not a reliable latency router.

Do not run all 13 instances during the presentation. A full runtime replication
is a rehearsal or pre-presentation validation task.

## Current known replication result

Luca's 2026-07-21 Docker Desktop run completed all 208 executions with matching
results and reported four winner flips relative to the accepted Colima
campaign: `q1_ai_yearly`, `q1_db_yearly`, `q3_direct_depth2`, and
`q5_ai_min2`. PostgreSQL remained faster on both Q2 instances, both deep-Q3
instances, both Q4 instances, and `q5_dm_min1`.

This supports two distinct conclusions:

1. semantic parity survived the environment change;
2. timing parity did not, especially for close comparisons.

It does not isolate Docker Desktop or Colima as the sole causal factor.

### Containerized Colima validation (2026-07-21)

The completed Compose workflow then reran all 13 instances under Colima with
the accepted 10-vCPU/8-GiB VM allocation, but with the benchmark client inside
the app container:

- 208/208 executions succeeded;
- every instance retained one stable, cross-backend result signature;
- campaign wall time was 58 minutes 51 seconds;
- PostgreSQL live/accepted median ratios ranged from 0.626× to 1.191×;
- Fuseki live/accepted median ratios ranged from 0.313× to 2.485×;
- three mechanical median winners changed: `q1_db_yearly` and
  `q1_ai_yearly` changed from PostgreSQL to Fuseki, while
  `q3_pvldb_distance3_depth2` changed from Fuseki to PostgreSQL.

The large workload asymmetries remained: PostgreSQL still won both Q2
instances, the dense/direct and deep Q3 instances, both Q4 instances, and both
Q5 instances. The complete local bundle is
`live-demo/runs/20260721T190238Z-colima/`.

This second replication is the decisive diagnostic point: a timing shift also
appears within the Colima runtime family when client placement and session
state change. The evidence therefore rejects a simple causal claim that
Docker Desktop alone produced the earlier differences.
