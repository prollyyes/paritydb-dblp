# PostgreSQL Q1-Q3 performance notes

This note summarizes Edoardo's PostgreSQL-only full-scale measurements. It does not compare PostgreSQL with Fuseki/SPARQL and makes no backend-selection claim.

## Measured medians

| Instance | Median (ms) | Rows |
| --- | ---: | ---: |
| Q1 all venues, decades | 207.438 | 15 |
| Q1 database venues, years | 30.498 | 30 |
| Q1 AI venues, years | 106.676 | 20 |
| Q2 all venues, minimum 2 | 2841.271 | 25 |
| Q2 database venues, minimum 3 | 1495.634 | 25 |
| Q3 direct moderate | 3014.644 | 1 |
| Q3 distance 3 | 2038.441 | 1 |
| Q3 out of bound, depth 2 | 2483.119 | 0 |

All first, warm-up, and measured executions returned stable normalized result hashes. The first observed executions are retained separately in `summary.csv`; they are not described as operating-system cold-cache measurements.

## Plan observations

- Q1 database-years completed in 31.322 ms in its separate plan capture and did not use temporary blocks. The all-venues/decades plan used 484 temporary read blocks and 485 temporary written blocks.
- Q2 plans use aggregate and sort work. The all-venues case showed an external merge in the recorded plan, with 1,808 temporary read blocks and 1,812 temporary written blocks; the database subset used 372 and 373 respectively.
- Q3 plans use the recursive SQL formulation. The direct, three-hop, and depth-bounded plan captures recorded temporary I/O, respectively: 15,594/15,672, 31,184/31,336, and 23,389/23,509 read/written blocks. The three-hop plan's separate `EXPLAIN (ANALYZE, BUFFERS)` execution took 6141.030 ms.

The plan files are collected after the timing campaign and are explanatory evidence only. They are not included in the measured timing statistics.
