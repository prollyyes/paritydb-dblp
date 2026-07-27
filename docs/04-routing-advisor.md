# The routing advisor: frozen rules, gated evidence, visible regret

The advisor is the piece the rest of the project was built to justify. The
pipeline gives us equivalent data, the contracts give us equivalent queries,
the campaign gives us trusted timings — and the advisor is where all of that
gets used to answer the practical question a developer actually has: *"I have
this kind of query; which backend should run it?"* This document explains how
`dm-advisor` works internally, why its rules are ordered the way they are,
what it refuses to claim without evidence, and what happened when we scored
it against the accepted campaign.

## Design position: recommendations are not measurements

The single most important decision here was made before any code: the
advisor's policy is **structural** and it was **frozen before we measured
anything** ([decision_matrix.md](decision_matrix.md) is the frozen artifact).
An advisor tuned after seeing the timings would be a lookup table wearing a
lab coat — it would "predict" its own training data and tell us nothing. By
freezing the rules first, the comparison between what the advisor *says* and
what the stopwatch *shows* becomes a genuine result, whichever way it lands.
Spoiler, discussed at the end: it landed badly for the structural intuition,
and we consider that the most interesting finding in the project.

The second decision follows from the first: a recommendation and a
performance claim are different objects. The advisor always answers with a
recommendation and a *reason*; it attaches latency numbers only when
correctness-gated evidence is supplied, and until then the output carries an
explicit warning that no measured evidence backs it. It never silently
upgrades an intuition into a fact.

## The inputs: structural profiles

`config/profiles.json` describes each of the five frozen query families as a
small feature vector — the features a developer could state about a workload
*before* running it:

| Profile | `aggregation` | `join_complexity` | `variable_path` | `needs_inference` |
|---|---|---|---|---|
| Q1 | true | `shallow` | false | false |
| Q2 | true | `self_join` | false | false |
| Q3 | false | `recursive` | true | false |
| Q4 | true | `bounded_traversal` | true | false |
| Q5 | true | `hierarchy` | false | true |

The features are deliberately coarse. We are not modeling cardinalities or
selectivities — that is what real optimizers do, and pretending to do it from
four booleans would be theater. The features capture the *shape* of a query:
does it aggregate, how do its joins relate tables, does it walk paths of
non-fixed length, does it need hierarchy/inference-style reasoning. Those are
exactly the properties people cite when they argue "this belongs in a graph
database", which is the folklore the project set out to test.

## The rules, and why their order matters

`recommend()` in `src/dm_project/advisor.py` is four rules checked in
sequence — first match wins:

1. **`needs_inference` → Fuseki.** The query follows a declared hierarchy;
   `rdfs:subClassOf*` states that in one line where SQL needs a recursive
   CTE (the Q5 contrast in [02-query-design.md](02-query-design.md)).
2. **`variable_path` → Fuseki.** Bounded or variable-length traversal is the
   graph pattern par excellence.
3. **`aggregation` with `shallow` or `self_join` joins → PostgreSQL.**
   Grouped tabular aggregation with ordinary joins is SQL's home turf.
4. **Otherwise → `run_both`.** No decisive structural signal; the honest
   answer is to measure, and the policy says so instead of guessing.

The ordering encodes "most structurally distinctive feature first", and it is
load-bearing. Q5 aggregates *and* follows a hierarchy: rule 1 must fire
before rule 3, because the hierarchy is what makes Q5 Q5 — the aggregation is
routine bookkeeping around it. Q4 likewise aggregates *and* traverses; the
two-hop pattern is its identity, so rule 2 outranks rule 3. If the rules were
ordered the other way, every family with a GROUP BY would collapse into
"PostgreSQL" and the policy would stop expressing anything about structure.
Under this ordering the five families split Fuseki = {Q3, Q4, Q5},
PostgreSQL = {Q1, Q2}, and `run_both` is reserved for future profiles that
genuinely match nothing.

Every rule returns a human-readable reason string alongside the backend, and
that string travels into every output. "Explainable" here means something
concrete: the answer always says *which structural property* drove it, so a
wrong recommendation can be traced to the rule that fired rather than to an
opaque score.

## The evidence gate

The advisor will decorate a recommendation with measurements only if the
caller points it at a benchmark summary, and the filter it applies
(`evidence()`) is strict on purpose. A summary row counts only if **all** of
these hold:

- same query family *and* same instance id — evidence for `q3_direct_depth2`
  says nothing about `q3_pvldb_out_of_reach`, and we saw exactly how much
  parameters matter within one family;
- same scale label — pilot numbers must never dress up a full-scale claim;
- `correctness_passed` is true — timing evidence downstream of the paired
  gate only;
- at least five successful measured runs — the protocol minimum, so no
  median computed from two lucky executions;
- if a dataset config is supplied (the CLI passes one by default), the row's
  dataset SHA-256 must match it — evidence is bound to the exact frozen
  dataset, not to "some DBLP subset";
- and finally, rows must survive for *both* backends. A one-sided median is
  not a comparison, so it is discarded entirely.

If anything fails, the advisor does not degrade gracefully into vagueness —
it returns the structural recommendation with the warning intact. We prefer
an output that admits ignorance to one that launders it.

When the gate passes, the output gains the per-backend medians, the measured
winner, and — when the recommendation names a concrete backend — the
**latency regret**: the recommended backend's median minus the best median,
in milliseconds. Zero regret means the structure-based advice matched the
stopwatch; a large regret quantifies exactly how expensive trusting the
folklore would have been for that instance. (`run_both` has no regret by
construction: it recommends measuring, not a backend.)

A typical gated call:

```bash
dm-advisor Q3 --scale full --instance q3_pvldb_distance3_depth4 \
    --summary results/final/summary.csv --dataset config/dataset.full.json
```

(The `--dataset` override matters: the default points at the pilot config,
whose hash would not match the full campaign's rows, and the gate would —
correctly — reject the evidence.)

returns JSON with `recommendation: "fuseki"`, the reason, both medians, the
measured winner (`postgresql`), no warning, and a regret of roughly 102
seconds — the advisor politely reporting the size of its own mistake.

## Scoring the frozen policy against the campaign

`results/tools/build_final_evaluation.py` runs the same `recommend()` over
all 13 accepted instances and writes `results/final/advisor_evaluation.csv`:
one row per instance with the recommendation, the reason, both medians, the
measured winner, a boolean `match`, and the regret. Because it reads the
audited campaign directly, no row carries a warning — this is the fully
evidenced view, and `fig3_advisor_regret.png` plots the regrets.

The score: the frozen structural policy matches the measured winner on
**5 of 13 instances**. The pattern behind the misses is consistent — every
large regret is a "Fuseki by structure, PostgreSQL by stopwatch" case:

- the two depth-4 Q3 instances (~102 s and ~94 s of regret), where the
  generated exact-depth SPARQL branches are dramatically more expensive than
  the recursive CTE;
- the two Q4 instances (~32 s and ~18 s), where the two-hop pattern reads
  beautifully in SPARQL and still loses by an order of magnitude;
- both Q5 instances, where the one-line `rdfs:subClassOf*` loses to the
  recursive closure by smaller but clear margins.

Meanwhile the rules got Q1/Q2 right (with the all-decades near-tie as the
one blemish) and Q3's shallow depth-2 control actually *did* go to Fuseki —
the structure signal is not noise, it is just not sufficient.

## What we take from this

It would have been easy to make the advisor look good: reorder the rules
after seeing the numbers, or swap rule 2's answer to PostgreSQL and call it a
day. We did not, because the miss *is* the result. What the evaluation
demonstrates, with frozen rules and audited evidence, is that expressiveness
and latency are different axes: the backend on which a query is most
*natural* to write was, for this engine, dataset, scale and our bounded-path
implementation, usually not the backend that answered fastest. A routing
policy built purely on structural folklore pays real, quantified regret —
which is the argument for advisors like this one that carry their evidence
with them and say plainly when they have none.

Two scope notes to keep the conclusion honest. First, the regrets are partly
a statement about *our* Q3 SPARQL strategy (exact-depth UNION branches, the
faithful cost of standard SPARQL's missing path lengths) and about in-memory
Fuseki 6.1.0 specifically — a different engine or a non-standard path
extension could shift them. Second, matching the measured winner on latency
is not the only sensible objective: if the criterion were query
maintainability, Q5's one-liner argues the other way. The advisor measures
one axis and names it; it does not pretend the axis is the whole decision.
