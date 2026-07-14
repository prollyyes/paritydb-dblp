# PostgreSQL evidence tools

These tools are scoped to Edoardo's Q1-Q3 PostgreSQL work.

## Load and schema evidence

```bash
python results/edo/tools/postgres_evidence.py \
  --canonical data/canonical \
  --output results/edo/pilot/postgres_evidence.json
```

The evidence collector verifies PostgreSQL counts against the canonical CSV and
metadata counts, then records server settings, schema constraints, indexes, and
table sizes.

## Semantic validation

```bash
python results/edo/tools/postgres_validate.py \
  --instances results/edo/pilot/instances.json \
  --output results/edo/pilot/semantic_validation.json
```

The validator independently checks:

- Q1 exact venue/bucket groups and counts reconstructed from raw publications.
- Q2 publication/co-author sets reconstructed in Python, thresholds, and
  deterministic ordering.
- Q3 bounded shortest distance against a separate in-memory breadth-first search over eligible PostgreSQL edges.

## Q3 instance selection

```bash
python results/edo/tools/postgres_select_q3.py \
  --dataset results/edo/pilot/dataset.json \
  --output results/edo/pilot/q3_selection.json
```

The selector builds the eligible undirected PostgreSQL graph once and
deterministically records a moderate-degree direct pair, a distance-3 pair with
a witness path, and the corresponding depth-2 out-of-bound case.

## Timed measurements

```bash
python results/edo/tools/postgres_benchmark.py \
  --instances results/edo/pilot/instances.json \
  --output-dir results/edo/pilot \
  --scale pilot \
  --warmups 2 \
  --repetitions 5
```

The runner records one first execution, two warm-ups, and five measured repetitions. It rejects incomplete runs and result-hash instability.

## Execution plans

```bash
python results/edo/tools/postgres_explain.py \
  --instances results/edo/pilot/instances.json \
  --output-dir results/edo/pilot/explain
```

Plans use `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` and are collected only after timed measurements finish.

The default endpoint is the isolated PostgreSQL service at `127.0.0.1:55432`.
