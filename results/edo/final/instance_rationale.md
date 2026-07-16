# Full-scale PostgreSQL Q1-Q3 instance rationale

The parameters in `instances.json` were frozen before semantic validation and timing. Person parameters are full DBLP IRIs, not display names.

## Q1

- `q1_all_decades` covers all five venues from 2005 through 2024 with decade buckets.
- `q1_database_years` covers SIGMOD, ICDE, and PVLDB from 2015 through 2024 with annual buckets.
- `q1_ai_years` covers KDD and NeurIPS for the same annual interval.

## Q2

- `q2_all_min_2` ranks authors over all venues with a non-trivial minimum of two publications.
- `q2_database_min_3` uses the database-venue subset and a minimum of three publications.

Both Q2 instances apply a deterministic ordering before the fixed limit of 25.

## Q3

The deterministic selection recorded in `q3_selection.json` uses the full eligible graph: 65,884 people with edges and 324,597 undirected collaboration edges.

- `q3_direct_moderate` uses Kenji Doya and Eiji Uchibe, each with eligible degree 3; the expected distance is 1.
- `q3_distance_3` uses Kenji Doya and Takayuki Katsuki; the archived witness path establishes distance 3.
- `q3_out_of_bound_depth_2` reuses the distance-3 endpoints with maximum depth 2, so the expected result is no row.

The direct, multi-hop, and bounded-no-result cases exercise the fixed Q3 SQL semantics without changing the eligible graph.
