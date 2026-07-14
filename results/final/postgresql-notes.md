# PostgreSQL Q1-Q3 plan notes

These `EXPLAIN (ANALYZE, BUFFERS)` executions were collected after the paired
campaign and are not benchmark measurements.

| Instance | Plan execution (ms) | Root node | Temp read/write blocks |
| --- | ---: | --- | ---: |
| `q1_all_decades` | 218.427 | Aggregate | 484 / 485 |
| `q1_db_yearly` | 48.440 | Aggregate | 0 / 0 |
| `q1_ai_yearly` | 121.244 | Aggregate | 0 / 0 |
| `q2_db_min3` | 720.894 | Limit | 371 / 371 |
| `q2_db_min5` | 626.249 | Limit | 372 / 373 |
| `q3_direct_depth2` | 16,037.144 | Aggregate | 23,389 / 23,511 |
| `q3_pvldb_distance3_depth4` | 14,418.156 | Aggregate | 1,004,600 / 4,441 |
| `q3_pvldb_distance3_depth2` | 171.105 | Aggregate | 2,616 / 327 |
| `q3_pvldb_out_of_reach` | 17,003.669 | Aggregate | 1,004,600 / 4,441 |

Q1 is grouped aggregation; its yearly subsets avoided temporary I/O. Q2 uses
aggregation, ordering, and a fixed limit, with modest temporary spilling in
these captures. Q3 uses the cycle-safe recursive CTE. The depth-4 PVLDB cases
materialize far more recursive and temporary-buffer work than the shallow
depth-2 control.

Plan execution time is explanatory evidence from one PostgreSQL execution. It
is not substituted for the five-run medians in `summary.csv`.
