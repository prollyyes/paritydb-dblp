# Pilot SQL instance rationale

The instances are frozen before semantic validation and timing. All person
parameters use full DBLP IRIs rather than display names.

## Q1

- `q1_all_decades` covers the complete five-venue, twenty-year pilot using the
  coarser decade grouping.
- `q1_database_years` narrows the workload to SIGMOD, ICDE, and PVLDB and uses
  annual buckets for 2015-2024.
- `q1_ai_years` covers KDD and NeurIPS with the same annual interval, providing
  a second venue grouping without changing Q1 semantics.

## Q2

- `q2_all_min_2` ranks authors across all venues with a low but non-trivial
  minimum-publication threshold.
- `q2_database_min_3` narrows to the three database venues and raises the
  threshold, exercising the same aggregate contract with a more selective
  parameter set.

Both Q2 instances use an exact limit of 25 after deterministic ordering.

## Q3

The eligible PostgreSQL graph has 12,691 people with at least one edge and
42,017 distinct undirected edges. Selection is deterministic and archived in
`q3_selection.json`.

- `q3_direct_moderate` uses Bryan Dawei He and Ioannis Mitliagkas. Each has
  eligible degree 3, and the expected shortest distance is 1.
- `q3_distance_3` uses Onur Yilmaz and Kelly Palmer. Each endpoint has eligible
  degree 5, and an independently selected witness path establishes distance 3.
- `q3_out_of_bound_depth_2` reuses the distance-3 endpoints with maximum depth
  2. The expected SQL result is no row, distinguishing bounded failure from a
  connected result without changing the eligible graph.
