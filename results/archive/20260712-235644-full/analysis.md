# Final campaign analysis — ParityDB-DBLP

Accepted campaign: `results/archive/20260712-235644-full` (working copies in this
directory). Scale `full`, dataset config SHA-256 `e8d99993…0c08`, instances SHA-256
`6b9e2b65…2cad`, timeout 300 s, 2 warm-ups, 5 measured repetitions, success = true.
Environment: see [environment.md](environment.md). Figures: [figures/](figures/).

## 1. Dataset

| | Pilot | Full (accepted) |
|---|---|---|
| Publications | 5,000 (1,000 × 5 venues, stratified) | 42,051 (every eligible publication) |
| Persons | 12,826 | 66,390 |
| Authorships | 20,492 | 173,986 |
| RDF triples | 66,176 | 475,002 |
| Excluded cross-listed | 0 | 0 |
| Excluded AmbiguousCreator | 1,080 | 5,894 |
| Missing primary names | 0 | 0 |
| Venue distribution | 1,000 each | NeurIPS 22,441 · ICDE 5,795 · KDD 5,762 · PVLDB 4,399 · SIGMOD 3,654 |

Source: DBLP RDF N-Triples 2026-06-01 (DOI 10.4230/dblp.rdf.ntriples.2026-06-01),
MD5 re-verified by the extractor on every run. Window 2005-2024. The full scale
removes `max_publications` ("every eligible publication" policy); the venue skew
toward NeurIPS is the real distribution and is reported rather than resampled.

## 2. Correctness

All 13 instances passed the SHA-256 normalized-equality gate at both scales; first-run
row counts per pair are identical. Full-scale row counts: Q1 = 15/57/39; Q2 = 25/25
(limit); Q3 = 1/1/0/0; Q4 = 18/6; Q5 = 19,659/3,960.

## 3. Median latency (5 measured runs, full scale)

| Instance | PostgreSQL | Fuseki | Winner | Ratio |
|---|---|---|---|---|
| q1_all_decades | 195.9 ms | **107.4 ms** | Fuseki | 1.8× |
| q1_db_yearly | 48.8 ms | **32.7 ms** | Fuseki | 1.5× |
| q1_ai_yearly | 120.9 ms | **62.7 ms** | Fuseki | 1.9× |
| q2_db_min3 | **447.6 ms** | 79,961.9 ms | PostgreSQL | 179× |
| q2_db_min5 | **1,279.6 ms** | 40,997.5 ms | PostgreSQL | 32× |
| q3_direct_depth2 | 13,702.0 ms | **9,595.7 ms** | Fuseki | 1.4× |
| q3_pvldb_distance3_depth4 | **7,425.2 ms** | 69,292.7 ms | PostgreSQL | 9.3× |
| q3_pvldb_distance3_depth2 | 201.4 ms | **71.2 ms** | Fuseki | 2.8× |
| q3_pvldb_out_of_reach | **7,477.8 ms** | 69,166.7 ms | PostgreSQL | 9.3× |
| q4_moderate_min1 | **1,361.7 ms** | 8,811.5 ms | PostgreSQL | 6.5× |
| q4_moderate_min2 | **1,832.2 ms** | 8,795.4 ms | PostgreSQL | 4.8× |
| q5_dm_min1 | **360.2 ms** | 575.4 ms | PostgreSQL | 1.6× |
| q5_ai_min2 | 695.9 ms | **380.3 ms** | Fuseki | 1.8× |

Warm behaviour is stable on both backends (max/min spread within ~3% for almost every
instance); first executions sit close to the measured medians (fig. 2), so no result
here hinges on cache state.

## 4. Expressiveness and structural notes

- **Q1 (grouping):** both languages express the bucketing directly; SPARQL needs an
  explicit `BIND`/`FLOOR` for decades where SQL uses integer division. Fuseki wins all
  three instances at full scale — grouped scans over the in-memory graph beat the
  relational aggregate here.
- **Q2 (aggregation + self-join):** the SQL CTE reads naturally; the SPARQL version
  needs a sub-SELECT plus an OPTIONAL co-author block, and counting *distinct
  co-authors per author* is where Fuseki collapses (179× on min3). The all-venue Q2
  variants were dropped after measurement: Fuseki exceeded the 300 s timeout at
  thresholds 2, 5 and 10 (documented exception; the campaign uses the
  SIGMOD/ICDE/PVLDB venue group instead).
- **Q3 (bounded shortest distance):** SPARQL 1.1 property paths cannot expose hop
  counts, so the harness generates exact-depth UNION branches — cheap at depth ≤ 2
  (Fuseki wins both shallow instances) but combinatorial at depth 4, where PostgreSQL's
  recursive CTE wins 9.3×. This is the clearest structure-vs-cost trade-off in the
  study. The dense-region direct pair is only viable at depth 2: at depth 4 the first
  campaign attempt timed out on Fuseki (>300 s) and took 17.1 s on PostgreSQL at pilot
  scale already.
- **Q4 (exact two-hop):** the graph pattern is the most readable formulation, but the
  double NOT-EXISTS/anti-join favours PostgreSQL (~5-6×). Seed selection matters: a
  high-degree NeurIPS seed (two-hop set 3,364) drove Fuseki past the timeout and was
  replaced by a moderate seed with the same selection criteria.
- **Q5 (hierarchy):** `rdfs:subClassOf*` states the closure in one line versus a
  recursive CTE in SQL; the outcome splits by result size (Fuseki wins the selective
  cross-area instance, PostgreSQL the 19,659-row retrieval-heavy one). "More natural"
  and "faster" remain separate claims.

## 5. Advisor evaluation

Full table: [advisor_evaluation.csv](advisor_evaluation.csv). Summary: the frozen
structural policy matched the measured winner on **5 of 13 instances**. Exceptions and
latency regret (recommended − best median): the two depth-4 Q3 instances dominate
(61.9 s and 61.7 s), followed by Q4 (7.4 s / 7.0 s), Q5 dm_min1 (215 ms) and the three
Q1 instances (16-89 ms, advisor picked PostgreSQL, Fuseki won). The advisor is
explainable rather than clairvoyant: its structural reasons remain true (the graph
pattern *is* the more direct expression for Q3/Q4), but expressiveness does not imply
lower latency on this engine pairing, dataset and scale — which is exactly the
distinction the project set out to measure.

## 6. Scope

Every conclusion above is scoped to: DBLP snapshot 2026-06-01 subset (42,051
publications, five venues, 2005-2024), the frozen query contracts, PostgreSQL 17.10
with the three schema indexes, Jena Fuseki 6.1.0 with an in-memory dataset, the
recorded machine, and the 1+2+5 timing protocol with full result retrieval.
