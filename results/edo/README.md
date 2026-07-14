# Edoardo benchmark evidence

This directory contains Edoardo's reproducible PostgreSQL evidence collected on the `edo/results` branch.

## Evidence policy

- Bulk DBLP source data, canonical CSV files, emitted RDF, and container storage are excluded from Git.
- Every accepted campaign preserves its dataset metadata, exact SQL instance configuration, raw PostgreSQL benchmark records, summary, query-result hashes, execution plans, campaign provenance, and environment description.
- A campaign is accepted only when Q1-Q3 pass their SQL semantic checks and PostgreSQL completes all measured repetitions.
- Pilot and final-scale evidence are stored separately.

## Layout

```text
results/edo/
  environment.md
  source_verification.md
  tools/
  pilot/
  final/
```

Each accepted scale preserves canonical verification and metadata, frozen
instances and rationales, PostgreSQL load/schema/index/config evidence,
independent semantic validation, raw and summarized measurements, timing
preflight notes, and execution plans with manifest hashes.

The evidence scope ends with PostgreSQL Q1-Q3 results and execution-plan observations.
