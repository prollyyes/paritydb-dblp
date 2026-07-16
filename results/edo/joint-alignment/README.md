# Edoardo PostgreSQL alignment to the joint campaign

This directory aligns Edoardo's assigned PostgreSQL work with the frozen final
campaign on `luca/experimental-campaign` at commit
`903ef0671a1eb13bd8bfefa401673513b1eb6af0`.

## Agreed project structure

- `results/final/` on the eventual integration branch is the sole paired
  PostgreSQL/Fuseki campaign used for evaluation medians and advisor regret.
- `results/edo/joint-alignment/` contains Edoardo's independent PostgreSQL
  load verification, Q1-Q3 SQL semantic checks, and execution plans.
- `results/edo/final/` remains the earlier independent PostgreSQL campaign. Its
  timings use different instances and are not merged into the paired campaign.

## Frozen contract

- Dataset file SHA-256: `e8d99993c461f36fa2a4c1114e74f5d3a50b8932cfced775110ba4afdd0c0c08`.
- Full instances SHA-256: `6b9e2b659ef172935ad3c3c609aa5ef6d9f7ac5e4f7b7b36c1a109d40dc82cad`.
- Edoardo Q1-Q3 projection SHA-256: `5ec556cdbd01ec290478cc62c487c896339fd58be614ab2f319b0309379bd344`.

`dataset.json` and `instances.json` are byte-for-byte copies of the joint
campaign contract. `instances-q1-q3.json` preserves the same Q1-Q3 instances
and ordering from that contract. It is a scope-filtered projection used only by
Edoardo's PostgreSQL alignment tools, which intentionally operate on his
assigned Q1-Q3 validation scope. Q4-Q5 remain present in the complete contract
and the accepted paired campaign.

The previously extracted canonical data records raw config SHA-256
`3e8b0875...50e4c`, while the joint contract records `e8d99993...0c08`.
Canonical JSON normalization gives both configuration files the same SHA-256,
`ac749c19...6da4`; the raw difference is formatting only. The pinned source,
selection policy, venues, areas, exclusions, and all canonical counts match.

## Alignment result

- PostgreSQL, canonical CSV, and metadata counts match.
- All nine frozen Q1-Q3 instances pass independent SQL semantic validation.
- For every instance, Edoardo's SQL result hash and row count equal both first
  results in the joint PostgreSQL/Fuseki campaign.
- Nine `EXPLAIN (ANALYZE, BUFFERS)` plans were collected after the joint timing
  campaign and are not benchmark measurements.
- No Fuseki/SPARQL command was executed during this alignment.

No new timing series is stored here. This prevents independent PostgreSQL runs
from being mixed with the single correctness-gated paired campaign used by the
evaluation.
