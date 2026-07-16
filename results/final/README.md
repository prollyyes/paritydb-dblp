# Accepted controlled final campaign

This is the sole paired PostgreSQL/Fuseki campaign used for evaluation and
advisor evidence. It supersedes the archived July 12 campaign and all
PostgreSQL-only timing tables under `results/edo/`.

- Frozen full dataset: 42,051 publications, 66,390 persons, 173,986
  authorships, 475,002 RDF triples.
- Frozen workload: 13 instances across Q1-Q5.
- Protocol: one first/correctness run, two warm-ups, five measured repetitions,
  300-second timeout, complete result retrieval, interleaved backend order.
- Environment: one 10-vCPU/8-GiB Colima VM with fresh PostgreSQL 17.10 and
  Fuseki 6.1.0 containers.
- Outcome: success, 208/208 executions, no timeouts or errors, and equal paired
  first-result hashes and row counts for every instance.

The campaign deliberately preserves substantial observed timing variability:
22 of 26 backend-instance series exceed the predeclared 10% spread flag. No
external disturbance or configuration change was identified, so every run is
retained and conclusions report medians together with min/max ranges.

Use `benchmark.csv` for raw evidence, `summary.csv` for medians and ranges,
`audit.json` for acceptance checks, and `advisor_evaluation.csv` for the frozen
policy evaluation. `evidence-sha256.json` makes the accepted evidence files
tamper-evident. PostgreSQL plans were captured after timing.
