# Advisor decision matrix

The structural policy is frozen before measurements. A recommendation is not a performance claim: the advisor displays a warning until a paired, correctness-gated benchmark summary is supplied.

| Condition | Recommendation | Explanation | Expected profiles |
|---|---|---|---|
| RDFS-style hierarchy required | Fuseki | The hierarchy is stated naturally as a graph path | Q5 |
| Bounded or variable traversal required | Fuseki | The graph pattern is the more direct expression | Q3, Q4 |
| Grouped tabular aggregation with shallow/self joins | PostgreSQL | SQL directly expresses grouping and aggregate filters | Q1, Q2 |
| No decisive structural rule | Run both | The policy does not pretend to have evidence | Future mixed profiles |

Evaluation uses the median measured time for the same instance. The measured winner is the lower median. Latency regret is `recommended median - best median`; it is reported only when both medians exist. Exceptions remain visible.

