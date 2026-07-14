# Pilot PostgreSQL Q1-Q3 performance notes

These observations describe only the PostgreSQL pilot. Plan execution occurred
after the accepted timed campaign and is not included in benchmark values.

## Timed results

| Family | Instance | Rows | First ms | Median ms | Min ms | Max ms |
|---|---|---:|---:|---:|---:|---:|
| Q1 | `q1_all_decades` | 15 | 20.992 | 18.755 | 18.620 | 18.866 |
| Q1 | `q1_database_years` | 30 | 5.646 | 5.480 | 5.336 | 5.617 |
| Q1 | `q1_ai_years` | 20 | 4.401 | 4.445 | 4.371 | 4.683 |
| Q2 | `q2_all_min_2` | 25 | 149.434 | 160.847 | 155.310 | 203.856 |
| Q2 | `q2_database_min_3` | 25 | 133.289 | 264.371 | 263.593 | 275.085 |
| Q3 | `q3_direct_moderate` | 1 | 87.244 | 77.027 | 72.287 | 95.438 |
| Q3 | `q3_distance_3` | 1 | 239.506 | 340.812 | 338.139 | 344.484 |
| Q3 | `q3_out_of_bound_depth_2` | 0 | 190.346 | 205.951 | 197.486 | 216.182 |

Every instance has five successful measured repetitions and one stable result
hash across its first, warm-up, and measured executions.

## Q1 plan observations

- `q1_all_decades` covers the full publication table. PostgreSQL chose a
  sequential scan of 5,000 rows, an in-memory quicksort, and sorted aggregation.
  The plan executed in 19.117 ms with 121 shared-buffer hits and no reads or
  temporary blocks.
- Both annual, venue-selective instances used bitmap index scans on
  `publication_venue_year_idx`, followed by bitmap heap scans, in-memory sorts,
  and sorted aggregation. The database and AI plans executed in 4.722 ms and
  3.808 ms respectively, with no temporary I/O.
- The all-venue sequential scan is reasonable at this pilot size because every
  publication qualifies; the index is used when the venue/year predicate is
  selective.

## Q2 plan observations

- Q2 must expand eligible authorships against coauthors before computing two
  distinct aggregates per person. The all-venue plan produced 112,952 rows in
  its left-join stage before aggregation; the database-only plan produced
  66,816.
- Both plans launched the two planned workers for a `Gather Merge`, used the
  `authorship_pkey` index-only scan, memoized coauthor lookups, filtered grouped
  authors by the minimum-publication threshold, and used an in-memory top-N
  heapsort for the exact limit of 25.
- The separate all-venue plan executed in 163.087 ms with 16,041 shared-buffer
  hits. The database-only plan executed in 108.690 ms with 9,723 hits. Neither
  plan performed shared-buffer reads or temporary I/O.
- `q2_database_min_3` showed a distinct timing phase: the first execution and
  first warm-up were 133.289 ms and 126.183 ms, the second warm-up was
  284.057 ms, and all five measured runs then stayed between 263.593 ms and
  275.085 ms. Its later standalone plan completed in 108.690 ms. This variation
  is preserved rather than attributed to one cause; parallel-worker scheduling
  and documented host background activity are plausible contributors.

## Q3 plan observations

- Every Q3 plan built the same 42,017 distinct undirected eligible edges from
  20,492 authorships using sequential scans, hash joins, and hashed aggregation.
  The edge aggregate used about 7 MB peak memory.
- The recursive CTE is cycle-safe through its visited array. PostgreSQL
  materialized the eligible-edge relation and repeatedly applied the endpoint
  `OR` join for each work-table frontier.
- The direct case generated four recursive rows and executed in 84.433 ms. Its
  top plan recorded 691 shared-buffer hits, no reads, and 364 temporary blocks
  written.
- The distance-3 case generated 1,406 recursive rows. Its recursive join removed
  619,400 candidate rows by the endpoint/cycle filter and rescanned the
  materialized edge set 59 times. It executed in 363.099 ms and recorded 21,170
  temporary blocks read and 365 written.
- The depth-2 out-of-bound case generated 59 recursive rows and correctly
  returned no result. It executed in 106.106 ms in the standalone plan, with
  1,825 temporary blocks read and 365 written.
- Depth and frontier expansion materially affect Q3 work even though the final
  result contains at most one row. These observations apply to the frozen pilot
  instances and are not universal PostgreSQL claims.

## Experimental limitations

- All plan pages were shared-buffer hits; the plans do not represent a cold
  operating-system or storage-cache state.
- The host was connected to AC power but was not fully idle. The exact
  preflight limitation is recorded in `timing_preflight.md`.
- `EXPLAIN (ANALYZE, BUFFERS)` adds instrumentation overhead and its execution
  times are reported only as plan context, not substituted for timed-campaign
  measurements.
