# The experimental campaign: protocol, validation, and what we measured

This document covers everything between "two loaded stores" and "defensible
numbers": the benchmark runner and its correctness gate, the choice of the 13
workload instances, Edoardo's independent PostgreSQL validation track, the
controlled final campaign that produced the accepted evidence in
`results/final/`, and how the routing advisor was evaluated against it. The
pipeline and query documents ([01](01-data-pipeline.md),
[02](02-query-design.md)) are assumed.

## Design goals for the protocol

Reading published micro-benchmarks left us with a checklist of failure modes
we wanted to rule out *by construction*, not by care:

1. **Timing wrong answers.** A backend that returns a different result set is
   not slower or faster — it is answering a different question.
2. **Hidden warm-up asymmetry.** If one backend's "first" run is secretly its
   third, cold-path costs vanish selectively.
3. **Ordering bias.** Always running backend A before backend B donates A's
   page-cache work to B (or steals from it).
4. **Incomparable timing boundaries.** Timing one engine server-side and the
   other end-to-end produces numbers that cannot be compared.
5. **Post-hoc selection.** Dropping "outlier" runs after seeing them is the
   quiet way to manufacture a winner.

Each of these maps to a specific mechanism below.

## The runner, mechanism by mechanism

`dm-benchmark` (`src/dm_project/benchmark.py`) drives both backends from one
process, reading the instance list from `config/instances.json` and the query
pair for each instance's family from `queries/`.

**The correctness gate (goal 1 and 2).** For every instance, the very first
execution on each backend is simultaneously the correctness check and the
recorded cold run — the code is explicit that no hidden query touches either
backend before it. Both first results are normalized and hashed (see the
query document for the normalizer); if row counts or SHA-256 hashes differ,
or either execution fails, the campaign *stops* — it does not skip the
instance and continue, because a correctness failure means the contract or a
loader is broken and every subsequent number would be suspect. Timed evidence
therefore exists only downstream of a passed gate.

**Scheduling (goal 3).** After the gate, each instance runs 2 warm-ups and
then the measured repetitions per backend (the CLI refuses fewer than 5
measured runs). Two policies exist: `blocked` (all of one backend, then all
of the other) and `interleaved`, which alternates which backend goes first
per run using the parity of instance index + run number, so neither backend
systematically inherits a warmed machine. The gate's own execution order also
alternates per instance under `interleaved`. The final campaign used
`interleaved`; the policy is recorded in `campaign.json` either way.

**The timing boundary (goal 4).** We deliberately time at the *client
result boundary* on both sides: for PostgreSQL, `execute()` plus a full
`fetchall()` over psycopg; for Fuseki, the HTTP POST to the query endpoint
plus reading and JSON-decoding the complete `application/sparql-results+json`
body. The clock (`time.perf_counter_ns`) stops when the client holds all
rows, before normalization and hashing. This is the only boundary that means
the same thing for a wire-protocol database and an HTTP triplestore; it does
include HTTP overhead for Fuseki, which we accept and state, because a real
application would pay it too. Both backends get the identical 300-second
budget: `statement_timeout` on the PostgreSQL session, socket timeout on the
Fuseki request.

**No selection (goal 5).** Every execution — first, warm-up, measured,
failed — is written to `benchmark.csv` with its elapsed time, row count,
result hash and error text. `summary.csv` reports median/min/max only for
series with the full number of successful measured runs, and nothing is ever
deleted. The campaign metadata (`campaign.json`) records the scale label,
SHA-256 of the dataset *and* instances files, timeout, repetition counts,
scheduling policy, and whether the campaign completed — enough to detect any
mixing of evidence from different configurations. A JSONL progress log
(instance started/completed events with UTC timestamps) is written strictly
outside the timed region.

## Choosing the 13 instances

The final workload (`config/instances.full.json`) has 13 instances across the
five families. The principle: every family gets at least two instances so no
conclusion hangs on one parameter point, and parameters are chosen to probe a
specific axis rather than to be "big".

- **Q1 × 3** — `q1_all_decades` (all venues, decade buckets: the coarsest,
  widest aggregation), `q1_db_yearly` (the three database venues, yearly) and
  `q1_ai_yearly` (KDD + NeurIPS, yearly). The split probes venue-set size and
  bucket granularity independently.
- **Q2 × 2** — `q2_db_min3` and `q2_db_min5` on the database venues. The
  threshold is the axis: raising `min_publications` shrinks the ranked set
  but *not* the aggregation work, and we wanted to see whether either engine
  exploits that.
- **Q3 × 4** — the family with the most instances because it has the most
  axes. `q3_direct_depth2`: a directly connected, high-degree pair over all
  venues (dense graph, shallow bound). `q3_pvldb_distance3_depth2`: a pair at
  true distance 3 searched with `max_depth` 2 — deliberately *not findable*,
  measuring the cost of exhausting a shallow budget. `q3_pvldb_distance3_depth4`:
  the same pair with the budget that does find it. `q3_pvldb_out_of_reach`: a
  pair beyond depth 4, the worst case that exhausts the full budget. The
  PVLDB pairs were not hand-picked: Edoardo's selection tool (below) chose
  them deterministically from the actual graph, with recorded witness paths.
- **Q4 × 2** — `q4_moderate_min1` and `q4_moderate_min2`, one
  moderate-degree source over all venues, varying only the mutual-count
  threshold.
- **Q5 × 2** — `q5_dm_min1` (ancestor `data-management`, a two-level subtree)
  and `q5_ai_min2` (ancestor `artificial-intelligence`, two child areas,
  threshold 2 forcing genuinely cross-area authors).

The instance files are hashed into the campaign evidence, so "the 13
instances" is not a loose phrase — it is SHA-256
`6b9e2b65…dc82cad`, pinned in the preflight record and in Edoardo's
alignment contract.

## Edoardo's independent PostgreSQL track

A paired benchmark where both implementations were written by the same
person, checked only against each other, has a blind spot: a *shared*
misreading of a contract would pass the gate. Edoardo's work under
`results/edo/` exists to close that hole for the PostgreSQL side of Q1–Q3,
with tools that reconstruct expected answers from first principles
(`results/edo/tools/`):

- **Load and configuration evidence** (`postgres_evidence.py`) — verifies
  table counts against both the canonical CSVs and `metadata.json`, then
  snapshots server settings, constraints, indexes and table sizes, so the
  exact engine state behind every plan and timing is on record.
- **Semantic validation** (`postgres_validate.py`) — the important one. Q1
  groups and counts are recomputed from raw publication rows; Q2
  publication/co-author sets are rebuilt in plain Python (sets and dicts, no
  SQL) including threshold and ordering; Q3 distances are recomputed by an
  independent breadth-first search over the eligible edge set. The SQL is
  thus checked against an implementation that shares none of its code or
  formalism.
- **Q3 instance selection** (`postgres_select_q3.py`) — builds the eligible
  undirected graph once and deterministically records a moderate-degree
  direct pair, a distance-3 pair *with its witness path*, and the matching
  out-of-bound case. This is how the final campaign's Q3 instances were
  chosen; publishing the witness path makes the "true distance 3" claim
  checkable by anyone.
- **Independent timing and plans** (`postgres_benchmark.py`,
  `postgres_explain.py`) — his own first/warm-up/measured runner against an
  isolated PostgreSQL instance (published on port 55432 so it could never
  collide with a shared service), plus `EXPLAIN (ANALYZE, BUFFERS, FORMAT
  JSON)` captures taken only *after* timing, since EXPLAIN executions would
  otherwise warm caches mid-campaign.

He ran this at pilot scale and at full scale (`results/edo/pilot/`,
`results/edo/final/`), and then produced `results/edo/joint-alignment/`: a
verification that his independently computed result hashes and row counts for
all nine frozen Q1–Q3 instances equal the first-run results of the joint
paired campaign, on the byte-identical dataset and instance contracts (the
one wrinkle — two config files with different raw SHA-256 that normalize to
the same canonical JSON — is documented there as formatting-only). Crucially,
the alignment adds **no timing series**: his independent PostgreSQL timings
use different instances and were never merged into the paired campaign, so
there is exactly one source of cross-backend numbers. The evidence-layout
policy in `results/README.md` enforces that separation.

## The controlled final campaign

The first full-scale paired campaign (July 12, preserved in
`results/archive/20260712-235644-full/`) was run on a developer machine in
everyday conditions. Reviewing it, we could not rule out interference —
other containers, changing resource allocation — so rather than defend it, we
froze a stricter environment and reran everything. That rerun is the
**accepted** campaign in `results/final/`; the archive is kept for the
replication comparison and is never mixed with it.

Controls for the rerun (full detail in `results/final/environment.md` and
`preflight.md`):

- One Colima VM with a fixed allocation — 10 vCPUs, 8 GiB — verified from
  both the host configuration and `nproc` inside the guest; only the two
  project containers running; AC power attached.
- Fresh PostgreSQL 17.10 and Fuseki 6.1.0 containers, loaded from one
  canonical extract immediately before the campaign; counts re-verified
  against `metadata.json` on both stores (42,051 publications / 66,390
  persons / 173,986 authorships; 475,002 triples in Fuseki).
- Pre-campaign commit hash, test-suite pass, dataset/instances SHA-256 and
  the re-verified official source MD5 recorded in the preflight before the
  first timed query.
- Frozen policy: first + 2 warm-ups + 5 measured runs per backend and
  instance, 300 s timeout, interleaved order, no mid-campaign changes.
  (Matplotlib, needed only for figures, was deliberately installed *after*
  timing.)

Outcome: all 13 instances passed the paired gate; 208/208 executions
succeeded (13 × 2 backends × (1 + 2 + 5)); no timeouts. About 75 minutes of
wall time, 4,502 seconds of timed query work.

### Acceptance is checked by a program, not a promise

`results/tools/build_final_evaluation.py` rebuilds every derived artifact
from the raw CSV and audits the campaign: exactly 208 raw rows, 26 measured
series of exactly 5 runs, 13 first-run pairs with matching hashes, and a
recomputation of every `summary.csv` median/min/max from the raw records.
The result is `audit.json` with an explicit `accepted` boolean. It also
regenerates the figures and finally writes `evidence-sha256.json`, a hash of
every file in `results/final/`, making the accepted evidence tamper-evident.
The PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` plans under
`results/final/postgresql-explain/` were captured after all timing, and the
notes there are careful to use them as *explanatory* evidence (where the
temp-buffer traffic goes in the deep Q3 cases), never as substitute timings.

### What the numbers say

Full tables in `results/final/analysis.md` and `summary.csv`; medians of five
measured runs:

- **Q1** is close, as expected for plain aggregation: PostgreSQL wins the two
  yearly subsets, and the all-venues decade case is a near tie (5.4 ms apart
  with overlapping ranges — we refuse to call that a Fuseki win).
- **Q2** is the largest gap in the workload: 0.5–1.4 s in PostgreSQL against
  80–139 *seconds* in Fuseki. The distinct-co-author self-join is simply a
  much better fit for a relational executor at this scale.
- **Q3** shows exactly the depth sensitivity the instances were designed to
  expose: Fuseki wins the shallow depth-2 PVLDB control (122 ms vs 215 ms),
  while PostgreSQL wins the dense direct case and both depth-4 cases by an
  order of magnitude or more — the generated depth-4 SPARQL branches with
  their quadratic distinctness filters are visibly expensive (110 s worst
  case).
- **Q4 and Q5** both go to PostgreSQL on latency (Q4 by roughly 10×, Q5 by
  1.6–3.7×), even though SPARQL is the terser language for both patterns.

One methodological finding matters as much as the rankings. The predeclared
variability check flags 22 of 26 series for spread above 10% of the median,
and comparison with the July 12 archive shows controlled-to-archived median
ratios from 1.47× to 3.99× for Fuseki and 0.96× to 1.80× for PostgreSQL, with
four instances flipping winner between campaigns. Since the two campaigns
differ in container runtime, allocation and scheduling, the evidence cannot
isolate a single cause — which is precisely why the analysis reports medians
*with* min/max ranges, keeps every run, and scopes every claim to the
recorded environment. Cross-campaign timing tables are not comparable and we
never merge them (`replication_comparison.csv` preserves the exact ratios).

## The advisor, and being honest about regret

The routing advisor (`dm-advisor`, policy in `config/profiles.json`,
rationale in [decision_matrix.md](decision_matrix.md)) recommends a backend
from *structural* features of a query profile — needs-inference, variable
path, aggregation with shallow/self joins — with rules frozen before any
measurement. It never claims performance on its own: a recommendation
carries a warning until it is paired with evidence, and the evidence gate is
strict — same family, same instance, same scale, same dataset hash,
correctness passed, at least five measured runs, both backends present.
When evidence is attached, the advisor reports its **latency regret**: its
recommended backend's median minus the best median.

Against the accepted campaign (`advisor_evaluation.csv`), the frozen policy
matches the measured winner on 5 of 13 instances, and the regrets are
dominated by the Q3 depth-4 instances (~102 s and ~94 s) and the two Q4
instances (~32 s and ~18 s). We want to be clear about why we publish that
number instead of tuning it away: the structural intuition "graph queries
belong on the graph engine" is *false on latency* for this engine, dataset
and bounded-path implementation, and demonstrating that with frozen rules is
the finding. Expressiveness (the one-line `rdfs:subClassOf*` against a
recursive CTE) and measured latency pull in opposite directions here, and a
routing policy that ignores measured evidence pays for it — which is exactly
the argument for advisors that carry their evidence with them.

## Scope, honestly stated

Everything above compares PostgreSQL 17.10 and in-memory Fuseki 6.1.0, on one
Apple M2 Pro under a fixed 10-vCPU/8-GiB VM, over one frozen DBLP subset,
one schema and index set, five frozen query contracts, and the documented
1 + 2 + 5 interleaved protocol. Within that scope the results are
reproducible from the pinned snapshot by following the README. Outside it —
other triplestores, TDB-backed Fuseki, other scales, tuned configurations —
we claim nothing.
