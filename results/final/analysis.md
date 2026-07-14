# Controlled final campaign analysis

## Dataset and protocol

The accepted campaign uses every eligible publication from the pinned June
2026 DBLP snapshot for five venues during 2005-2024: 42,051 publications,
66,390 persons, 173,986 authorships, and 475,002 RDF triples. Both stores were
loaded fresh from the same canonical CSV extract.

All 13 instances passed normalized paired correctness. The campaign contains
exactly 208 successful executions: one first/correctness run, two warm-ups, and
five measured runs for each backend and instance. Total timed query work was
4,502.099 seconds; the complete campaign took approximately 75 minutes.

## Median latency

| Instance | PostgreSQL (ms) | Fuseki (ms) | Median winner |
| --- | ---: | ---: | --- |
| `q1_all_decades` | 209.574 | 204.131 | Fuseki (near tie) |
| `q1_db_yearly` | 49.465 | 100.736 | PostgreSQL |
| `q1_ai_yearly` | 115.817 | 141.887 | PostgreSQL |
| `q2_db_min3` | 508.687 | 138,693.932 | PostgreSQL |
| `q2_db_min5` | 1,429.086 | 79,677.175 | PostgreSQL |
| `q3_direct_depth2` | 14,771.384 | 21,725.391 | PostgreSQL |
| `q3_pvldb_distance3_depth4` | 8,368.978 | 110,097.174 | PostgreSQL |
| `q3_pvldb_distance3_depth2` | 215.111 | 122.124 | Fuseki |
| `q3_pvldb_out_of_reach` | 7,893.591 | 101,906.540 | PostgreSQL |
| `q4_moderate_min1` | 1,490.132 | 19,097.812 | PostgreSQL |
| `q4_moderate_min2` | 3,289.884 | 35,070.092 | PostgreSQL |
| `q5_dm_min1` | 406.087 | 1,488.390 | PostgreSQL |
| `q5_ai_min2` | 902.041 | 1,437.111 | PostgreSQL |

The Q1 all-decades medians differ by only 5.443 ms and both series have broad,
overlapping min/max ranges, so it is treated as a near tie rather than strong
evidence for Fuseki. Q2 strongly favours PostgreSQL for the distinct-coauthor
aggregation. Q3 shows the intended depth sensitivity: Fuseki wins the shallow
PVLDB control, while PostgreSQL wins the dense direct case and both depth-4
cases. PostgreSQL also wins Q4 and both Q5 instances on median latency, although
SPARQL remains the more direct language for the graph and hierarchy patterns.

## Variability and replication

The predeclared spread check flags 22 of 26 series because `(max-min)/median`
exceeds 10%. Fuseki shows the largest spreads, while PostgreSQL is stable for
the expensive Q3 cases but variable in Q4 minimum-2. No timeout, service
restart, competing container, power interruption, or mid-campaign change was
observed. All measurements are therefore preserved; no run was discarded or
selected post hoc.

Absolute timings differ materially from the archived July 12 campaign, and
four median winners changed: Q1 database-yearly, Q1 AI-yearly, Q3 direct-depth-2,
and Q5 AI-minimum-2. Relative to the archive, controlled Fuseki medians range
from 1.473x to 3.987x, while PostgreSQL ranges from 0.958x to 1.796x. The
campaigns used different container runtimes, resource allocation, scheduling
policy, and sessions; the evidence does not isolate one of these as the sole
cause. This confirms that old branch-specific timing tables must not be mixed
with this accepted campaign. Claims are scoped to the recorded 10-vCPU Colima
environment and include the observed min/max ranges. Exact ratios are preserved
in `replication_comparison.csv`.

## Advisor evaluation

The frozen structural advisor matches the median winner on 5 of 13 instances.
Its largest regrets are the two depth-4 Q3 instances (101,728.196 ms and
94,012.949 ms), followed by Q4 minimum-2 (31,780.208 ms) and Q4 minimum-1
(17,607.680 ms). This is not a defect hidden by retuning: the structural rules
were frozen before measurement. The result demonstrates that a more natural
SPARQL expression does not necessarily imply lower latency for this engine,
dataset, and bounded-path implementation.

## Scope

These results compare PostgreSQL 17.10 and in-memory Fuseki 6.1.0 on one Apple
M2 Pro machine, the frozen DBLP subset, fixed schema/indexes, fixed query
contracts, and the documented interleaved 1+2+5 protocol. They are not a
universal ranking of relational databases and RDF triplestores.
