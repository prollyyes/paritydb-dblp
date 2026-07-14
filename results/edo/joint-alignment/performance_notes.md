# Aligned PostgreSQL Q1-Q3 plan notes

These are PostgreSQL-only observations from `EXPLAIN (ANALYZE, BUFFERS)` on the
jointly frozen instances. Plan executions occurred outside benchmark timing.

| Instance | Plan execution (ms) | Root node | Temp read/write blocks |
| --- | ---: | --- | ---: |
| `q1_all_decades` | 216.355 | Aggregate | 484 / 485 |
| `q1_db_yearly` | 47.468 | Aggregate | 0 / 0 |
| `q1_ai_yearly` | 112.757 | Aggregate | 0 / 0 |
| `q2_db_min3` | 549.283 | Limit | 0 / 0 |
| `q2_db_min5` | 535.591 | Limit | 0 / 0 |
| `q3_direct_depth2` | 15860.598 | Aggregate | 23,388 / 23,503 |
| `q3_pvldb_distance3_depth4` | 14015.442 | Aggregate | 1,004,600 / 4,441 |
| `q3_pvldb_distance3_depth2` | 143.959 | Aggregate | 2,616 / 327 |
| `q3_pvldb_out_of_reach` | 14140.685 | Aggregate | 1,004,600 / 4,441 |

Q1 uses grouped aggregation, and the database/AI yearly subsets avoid temporary
I/O in these captures. Q2 combines aggregation, ordering, and a fixed limit.
Q3 uses the cycle-safe recursive formulation; the depth-4 PVLDB cases perform
substantially more recursive and temporary-buffer work than the depth-2 case.

These plan times explain one PostgreSQL session only. Evaluation medians remain
those from the single paired final campaign, and no cross-backend conclusion is
derived from plan time.
