# Live demo — ParityDB-DBLP

Terminal-only demo in three beats, plus an optional live re-execution of the
benchmark. Everything runs from the repository root through
`live-demo/demo.sh` and leaves **no files behind**: the benchmark runner
needs a working file, so the script points it at a temporary directory that
is deleted on exit. Nothing inside the repository (in particular
`results/final/`) is ever written.

```bash
live-demo/demo.sh 1     # beat 1: live paired run (correctness gate + timings)
live-demo/demo.sh 2     # beat 2: advisor on Q5
live-demo/demo.sh 3     # beat 3: advisor on deep Q3
live-demo/demo.sh all   # all three, pausing for ENTER between beats
```

## The three beats

### Beat 1 — the correctness gate, live (~9 s of execution)

Runs the real campaign protocol (1 first/correctness run, 2 warm-ups, 5
measured repetitions, interleaved backend order) on the single instance
`q5_ai_min2`, against the live PostgreSQL and Fuseki services.

What to point at on screen:

- the `first` rows: the correctness gate — both backends return **3,960 rows**
  with the **same SHA-256 result hash**; a mismatch would abort the campaign;
- every subsequent run repeats the same row count and hash;
- the timings exist *only after* equality has been established.

Say: "This is the exact protocol of the accepted campaign, on one instance.
Before any timing is recorded, both backends must return semantically equal
results — same row count, same normalized hash. Only then do warm-ups and
measured repetitions run."

**Important — live timings will not match the campaign.** See "Live timings
on this hardware" below before rehearsing this beat.

### Beat 2 — the advisor explains and admits (~0 s)

`dm-advisor Q5 --instance q5_ai_min2` reads only committed evidence
(`results/final/summary.csv`); services are not needed.

What to point at in the JSON:

- `recommendation: fuseki` with a human-readable structural `reason`;
- `evidence.measured_winner: postgresql` — the measurement disagrees;
- `latency_regret_ms: 535.07` — the quantified cost of following the rule.

Say: "The advisor recommends Fuseki because the query follows a declared
hierarchy — a transparent, frozen rule. Then it attaches the correctness-gated
evidence: the measured winner was PostgreSQL, and following the recommendation
would have cost 535 milliseconds. Recommendation and measurement are kept
separate on purpose."

### Beat 3 — the same policy, the disastrous case (~0 s)

`dm-advisor Q3 --instance q3_pvldb_distance3_depth4`, again evidence replay
only — no waiting for the ~110 s Fuseki execution.

What to point at:

- same structure as beat 2, same frozen policy;
- `latency_regret_ms: 101728` — the regret is now **101.7 seconds**.

Say: "Same policy, different instance: for deep bounded traversal the
structural rule recommends Fuseki again, but here following it would cost a
hundred seconds. This is why our conclusion is that query shape alone is not
enough to route queries — which is exactly the negative result on the next
slide." (Hand back to the slides.)

## Re-executing the benchmark live

`demo.sh run` re-executes the real benchmark (same protocol, same correctness
gate) on a chosen subset and then compares the live medians against the
accepted campaign, flagging every instance whose winner flips:

```bash
live-demo/demo.sh run --all              # every instance  (~40 min, CPU at 100%)
live-demo/demo.sh run Q1                 # one family      (~10 s)
live-demo/demo.sh run Q1 Q5              # several families
live-demo/demo.sh run q3_direct_depth2   # a single instance
live-demo/demo.sh run Q5 q1_db_yearly    # families and instances mix freely
```

Family and instance names are validated against `config/instances.full.json`;
an unknown token aborts before anything runs. When the run completes, the
comparison (`live-demo/compare.py`) prints per-instance medians for both
environments plus a `WINNER FLIP` marker; the raw CSV lives in the temporary
directory and disappears with it.

**Measured durations** (M2 Pro, Docker Desktop, full scale, 2026-07-21 —
the script prints an estimate before starting):

| Selection | Wall clock |
|---|---|
| `--all` (13 instances) | **~40 min** |
| `Q1` (3 instances) | ~10 s |
| `Q2` (2 instances) | ~15 min |
| `Q3` (4 instances) | ~22 min |
| `Q4` (2 instances) | ~3 min |
| `Q5` (2 instances) | ~20 s |

The expensive individual instances are `q2_db_min3` (~10 min),
`q3_pvldb_distance3_depth4` and `q3_pvldb_out_of_reach` (~9.5 min each),
`q2_db_min5` (~5 min) and `q3_direct_depth2` (~3 min); everything else runs in
seconds. During a run the machine sits near 100% CPU: close other work, keep
AC power attached, and do not run it *during* the presentation — the guide's
rule stands ("do not rerun the benchmark during the presentation").

## Live timings on this hardware (2026-07-21 full re-execution)

We re-ran all 13 instances on the demo laptop (`demo.sh run --all`) and
compared against the accepted campaign:

```
instance                        live PG    live FU   live win    camp PG    camp FU   camp win
q1_ai_yearly                      107.3       55.4     fuseki      115.8      141.9 postgresql  <-- FLIP
q1_all_decades                    179.5      104.7     fuseki      209.6      204.1     fuseki
q1_db_yearly                       45.4       31.0     fuseki       49.5      100.7 postgresql  <-- FLIP
q2_db_min3                        456.0    74961.0 postgresql      508.7   138693.9 postgresql
q2_db_min5                       1297.2    37610.9 postgresql     1429.1    79677.2 postgresql
q3_direct_depth2                13659.7     9050.0     fuseki    14771.4    21725.4 postgresql  <-- FLIP
q3_pvldb_distance3_depth2         200.5       70.5     fuseki      215.1      122.1     fuseki
q3_pvldb_distance3_depth4        7484.2    62815.9 postgresql     8369.0   110097.2 postgresql
q3_pvldb_out_of_reach            7441.6    62406.3 postgresql     7893.6   101906.5 postgresql
q4_moderate_min1                 2752.9     8150.9 postgresql     1490.1    19097.8 postgresql
q4_moderate_min2                 1838.0     8107.4 postgresql     3289.9    35070.1 postgresql
q5_ai_min2                        675.5      377.9     fuseki      902.0     1437.1 postgresql  <-- FLIP
q5_dm_min1                        334.8      551.6 postgresql      406.1     1488.4 postgresql
```

- **Correctness: 208/208 executions succeeded and every instance passed the
  gate** — identical row counts and SHA-256 hashes on both backends. Parity
  is environment-independent.
- **Timings are not**: PostgreSQL ran ~10-15% faster than the campaign,
  Fuseki **2-4× faster** (e.g. `q2_db_min3` 138.7 s → 75.0 s;
  `q3_pvldb_distance3_depth4` 110.1 s → 62.8 s; `q5_ai_min2` 1,437 ms → 378 ms).
- **4 winner flips, all PostgreSQL → Fuseki, all in already-close races**:
  `q1_ai_yearly`, `q1_db_yearly`, `q3_direct_depth2`, `q5_ai_min2`.
- **The structural asymmetries survive**: Q2 remains catastrophic for Fuseki
  (58-164× slower), deep Q3 remains ~8× in favour of PostgreSQL, and the Q3
  winner still depends on the depth parameter.

Why the difference: same hardware (MacBook Pro M2 Pro, 16 GB), different
environment. The campaign ran in a provisioned Colima VM (vz, Docker 27.4,
exactly 10 vCPU / 8 GiB, fresh dedicated containers — see
`results/final/environment.md`); the demo machine runs Docker Desktop
(Docker 29.2, different VM networking). Fuseki timings include full HTTP
result retrieval, so the VM network path affects them far more than the
PostgreSQL binary protocol.

How to use this on stage: the live winner of a close race (including
`q5_ai_min2` in beat 1) may contradict the campaign — say so *before* it
happens: "live timings on an uncontrolled laptop are illustrative; close-race
winners are a property of the environment, the large asymmetries are a
property of the workload. The authoritative evidence is `results/final/`,
whose environment is recorded line by line." This is slide 11 demonstrating
itself.

## What the demo needs running

- **Beat 1 and `run` are the only parts that touch the services**: they need
  the two Docker containers up *and the data loaded*. Everything is local —
  no network access is involved.
- **Beats 2 and 3 need nothing running**: the advisor only reads the committed
  `results/final/summary.csv` and `config/` files.

## Reproducing from a fresh clone

Anyone can reproduce the demo by following the repository quickstart
(`README.md`, "Environment" and "Build the equivalent datasets"):

```bash
docker compose up -d --build            # PostgreSQL + in-memory Fuseki
dm-extract /path/to/dblp-2026-06-01.nt.gz   # pinned snapshot, kept outside Git
dm-emit-rdf
dm-load-postgres --canonical data/canonical-full
dm-load-fuseki data/rdf/dataset-full.nt
live-demo/demo.sh all
```

With the canonical data already extracted, tearing down and rebuilding the
whole stack takes about 20 seconds (measured: compose down 1 s, up 3 s,
PostgreSQL load 5 s, Fuseki load 2 s).

Mind one detail: **the Fuseki dataset lives in memory**. If the Fuseki
container is recreated or restarted, rerun `dm-load-fuseki` before beat 1
(and rerun `dm-load-postgres` if the PostgreSQL container was recreated, since
the Compose file declares no named volume). The script resolves the mapped
Postgres port automatically (override with `PG_PORT` or `DSN` env vars).

## Preflight checklist

1. `docker compose ps` — both services `Up`.
2. Both stores loaded (see above) — rerun the loaders if a container was
   recreated.
3. Terminal at repository root, project environment active, font large enough.
4. One rehearsal run of `live-demo/demo.sh all` the same morning.
5. `results/final/summary.csv` committed and present (beats 2-3 depend only on
   this).
