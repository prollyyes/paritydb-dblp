# Query design: the five families, line by line

This document explains every query in `queries/`, why each one is written the
way it is, and the traps we hit while making the SQL and SPARQL versions
return byte-identical results. The binding semantic definitions live in
[query_contracts.md](query_contracts.md); this is the narrative behind them.

A note on how to read this: for each family we state the analytical question,
then walk the SQL, then the SPARQL, then the equivalence pitfalls. The
pitfalls sections are where most of our debugging hours went, so they are the
least skippable part.

## How parameters reach the queries

The two backends take parameters through completely different mechanisms, and
we kept both idiomatic instead of inventing a common denominator:

- **SQL** uses psycopg's server-side named parameters (`%(year_from)s` and
  friends). Venue sets are passed as a real array and matched with
  `venue_id = ANY(%(venue_ids)s)`. Nothing is string-interpolated, so there
  is no injection surface and the planner sees stable query shapes.
- **SPARQL** has no standard parameter binding for this use case, so the
  runner renders `{{placeholder}}` templates. This is more dangerous, and we
  treat it accordingly: IRIs are serialized through rdflib's `n3()` (which
  validates and brackets them), the `ancestor_area` slug — the one value that
  is spliced into an IRI — must match `[a-z0-9-]+` or rendering aborts, and
  after substitution the runner scans for any leftover `{{...}}` placeholder
  and fails loudly rather than sending a broken query.

Venue sets appear in SPARQL as an inline `VALUES ?venue { ... }` block. The
special value `"all"` in an instance expands to all five configured streams on
both sides, from the same `dataset.json`, so the two backends can never
disagree about what "all venues" means.

## How results are compared

Every execution's rows pass through one normalizer before hashing
(`benchmark.normalize`): `None` becomes the empty string, columns declared
integer-valued (`bucket_start`, `publication_count`, `coauthor_count`,
`distance`, `mutual_coauthor_count`, `area_count`) are canonicalized through
`str(int(v))`, everything else is stringified, rows are sorted by their full
content, and the result is hashed as canonical JSON (SHA-256).

Two consequences worth spelling out:

1. The integer canonicalization exists because psycopg returns Python `int`s
   while Fuseki's JSON results give us decimal *strings* — and SPARQL
   aggregates can even come back with different lexical forms. Without it,
   `2010` vs `"2010"` would fail every comparison.
2. Rows are sorted before hashing, so the hash does not test *ordering*. That
   is intentional — but it means any query with a `LIMIT` must have a total,
   deterministic `ORDER BY`, because otherwise the two backends could pick
   different tie rows and produce genuinely different sets. This is why every
   ranked query below ends its ordering with the person IRI: it is the one
   key guaranteed unique.

## Q1 — Publication trends (grouped aggregation)

*How many publications did each venue produce per year, or per decade?*

This is the baseline family: a filter, a group-by, a count. If a backend
struggled here the rest would be moot.

**SQL** (`queries/sql/q1.sql`). A single scan of `publication` filtered by
year window and venue array, grouped by venue and bucket. The bucket is a
`CASE`: for `'decade'` it is `(p.year / 10) * 10` — integer division makes
this the floor of the decade, per the contract — otherwise the year itself.
`COUNT(DISTINCT publication_id)` rather than `COUNT(*)`: with the current
schema each publication appears once, so they are equivalent today, but the
`DISTINCT` makes the query's meaning independent of that assumption (and
matches the SPARQL side textually in intent).

**SPARQL** (`queries/sparql/q1.rq`). The same shape: a `VALUES` block for the
venue set, two triple patterns (`publishedInStream`, `yearOfPublication`), a
year-window `FILTER`, and a `BIND` computing the bucket with
`FLOOR(year / 10) * 10` behind an `IF` on the bucket parameter. One
asymmetry: SQL gets the bucket mode as a comparison against a bound
parameter, while SPARQL compares two rendered string literals
(`"decade" = "decade"`) — constant-folded by the engine, and semantically the
same switch.

**Pitfalls.** This family is where the `xsd:gYear` problem first appeared.
Years in the graph are typed `"2015"^^xsd:gYear`, and in SPARQL you cannot
compare a gYear literal with an integer, nor cast gYear to integer directly.
The portable route we settled on — used in every family — is
`xsd:integer(STR(?year))`: take the lexical form, then cast. Ugly, but
correct, and it keeps the RDF faithful to DBLP's actual schema instead of
dumbing the data down to plain integers to make querying easier.

## Q2 — Productive authors and their co-author reach (aggregation + self-join)

*Which authors published at least N times in the selected venues, and how
many distinct co-authors did each accumulate?*

**SQL** (`queries/sql/q2.sql`). Three stages as CTEs. `eligible_publications`
applies the venue/year filter once. `author_stats` joins `authorship` to it,
then `LEFT JOIN`s `authorship` *again* on the same publication — the
self-join that pairs each author with everyone else on the paper — and
computes two aggregates: distinct publications, and distinct co-author IDs
using a `FILTER (WHERE co.person_id <> a.person_id)` clause. The `LEFT JOIN`
plus filtered aggregate combination is deliberate: an author whose eligible
papers are all single-authored must be *kept* with a co-author count of 0,
not dropped by an inner join. The outer query joins to `person` only at the
end (names are pure display data, no reason to drag them through the
aggregation), applies the `min_publications` threshold, and orders by
publication count desc, co-author count desc, person IRI — the IRI tiebreak
making the `LIMIT` deterministic, as explained above.

**SPARQL** (`queries/sparql/q2.rq`). The same three stages, expressed the way
SPARQL wants them. An inner sub-`SELECT` computes per-author distinct
publication counts and applies the threshold with `HAVING` — putting the
threshold *inside* the subquery matters, both semantically (the contract says
the threshold applies to the publication count alone) and practically (it
shrinks the set of authors for whom the expensive co-author block runs). The
outer pattern fetches the display name, then an `OPTIONAL` block re-matches
eligible publications by that author together with each `?coauthor`,
filtering out self-pairs. `OPTIONAL` is the graph-side twin of the `LEFT
JOIN`: a solo author leaves `?coauthor` unbound, and
`COUNT(DISTINCT ?coauthor)` over unbound is 0, matching SQL exactly.

**Pitfalls.** Our first SPARQL draft computed both counts in one flat pattern
and was wrong twice: `HAVING` on one aggregate while projecting another gets
awkward, and dropping `OPTIONAL` silently removed sole authors — a mismatch
the correctness gate caught on first contact, which was satisfying
confirmation that the gate earns its keep. Also note the venue/year filter is
*repeated inside* the co-author block: co-authorship must be established on
eligible papers only, so the filter belongs to both patterns, not just the
subquery.

## Q3 — Bounded collaboration distance (recursive traversal)

*What is the minimum number of collaboration edges between two given
researchers, if it is at most `max_depth`?*

This family is the heart of the project and consumed more design time than
the other four combined. Both backends are outside their comfort zone in
opposite directions: SQL has recursion but no native graph, SPARQL has graph
patterns but — surprisingly — no way to get a path *length*.

The collaboration edge is defined once, in the contract, for Q2–Q4 alike: two
distinct people share one undirected edge iff they co-authored at least one
eligible publication. Multiplicity never adds edges.

**SQL** (`queries/sql/q3.sql`). First, `eligible_edges` materializes the edge
set: a self-join of `authorship` on the publication (with `a1.person_id <
a2.person_id` to keep each unordered pair once), and the canonical form
`LEAST(person_a, person_b) / GREATEST(...)` with `SELECT DISTINCT` collapsing
multiplicity. Then a recursive CTE `paths(current_id, distance, visited)`
does the walk: the base case seeds the source at distance 0; the recursive
step expands to the neighbour on either side of an incident edge (the
`CASE WHEN e.left_id = p.current_id THEN e.right_id ELSE e.left_id END`
dance, needed because edges are stored canonically, not symmetrically),
bounded by `distance < max_depth`. The `visited` array is the crucial bit:
appending each reached node and refusing to revisit
(`NOT (... = ANY(p.visited))`) makes the recursion cycle-safe — without it, a
dense co-authorship graph recurses forever. Restricting to simple paths loses
nothing because some shortest path is always simple. The final `SELECT` takes
`MIN(distance)` over rows that reached the target, and the `HAVING MIN(...)
IS NOT NULL` clause turns "unreachable within budget" into *zero rows* rather
than a NULL row — that exact shape is what the contract requires and what the
SPARQL side naturally produces, so the hashes agree.

**SPARQL** (`queries/sparql/q3.rq` + `benchmark.build_path_branches`). Here
is the honest limitation we ran into: SPARQL 1.1 property paths can test
reachability (`(:knows)+`), but the standard gives you no way to ask *how
long* the path was. Since Q3's answer *is* the length, property paths alone
cannot implement the contract. We considered three ways out: (a) issue one
reachability query per depth from the client and stop at the first hit —
rejected, because it turns one measured query into up to `max_depth` HTTP
round-trips and times the client loop, not the engine; (b) relax the
contract to boolean reachability — rejected, it would flatten the most
interesting family; (c) generate, for a given `max_depth`, one exact-depth
graph pattern per length and `UNION` them, letting the engine pick the
minimum. We went with (c): the template has a `{{path_branches}}` slot the
runner fills with `max_depth` branches; the branch for depth *k* binds
`?node0` to the source and `?nodek` to the target, chains *k* eligible
publications (each `?paper_i` authored by both `?node_{i-1}` and `?node_i`,
in the venue set and year window), and asserts pairwise distinctness over all
nodes on the path — again sound because shortest paths are simple, and
necessary because without it a depth-3 branch could match a depth-1 pair by
stuttering. Each branch binds its depth as `?candidate_distance`;
`MIN(?candidate_distance)` over the union is the answer, and the
`HAVING(COUNT(...) > 0)` clause yields zero rows when nothing matched. The
degenerate source = target case is short-circuited to `BIND(0 AS
?candidate_distance)` at render time (distance zero, per the contract).

**Pitfalls.** The pairwise-distinctness filter grows quadratically with
depth — at `max_depth` 4 that is 10 inequality pairs on the deepest branch —
and the branch sizes are visible in the measured latencies (the campaign
document returns to this). We kept it anyway: this is the *faithful* cost of
expressing "bounded shortest distance" in standard SPARQL, and papering over
it would misrepresent the language. Fairness is preserved by construction:
`max_depth` bounds both sides equally, the same edge eligibility applies, and
the generated SPARQL is deterministic given the parameters.

## Q4 — Indirect collaborator discovery (exact two-hop pattern)

*Who is at exactly collaboration distance two from a given researcher — a
co-author of a co-author, but never a direct co-author — and through how many
mutual colleagues?*

Where Q3 is variable-depth, Q4 fixes the depth at exactly 2 and turns the
result into a ranking. It is the "recommend people you may know" query.

**SQL** (`queries/sql/q4.sql`). Reuses the same canonical `eligible_edges`
CTE as Q3 verbatim — one definition of collaboration, one implementation per
backend. Because the two-hop walk needs to leave *from* a node regardless of
which side of the canonical edge it sits on, a `neighbours` CTE first unfolds
each edge into both directed forms (`UNION ALL` of the pair and its swap;
`ALL` because the canonical form guarantees no duplicates, so a dedup pass
would be wasted work). Then `candidates` joins `neighbours` to itself:
first hop from the source to `?mutual`, second hop from `?mutual` to the
candidate; the candidate must not be the source, and a `NOT EXISTS` against
`neighbours` removes anyone directly connected to the source — that is what
makes the distance *exactly* two rather than *at most* two.
`COUNT(DISTINCT first.neighbour_id)` counts mutual connectors per candidate;
the outer query applies `min_mutuals`, attaches names, and orders by mutual
count desc then candidate IRI (the usual deterministic-LIMIT discipline).

**SPARQL** (`queries/sparql/q4.rq`). The two hops are two publication
patterns sharing `?mutual`: `?firstPaper` authored by the source and
`?mutual`, `?secondPaper` authored by `?mutual` and `?candidate_id`, each
with its own venue `VALUES` and year filter (eligibility applies per edge,
exactly as in the SQL edge set). Inequality filters exclude the degenerate
identities (mutual ≠ source, candidate ∉ {source, mutual}), and a
`FILTER NOT EXISTS` block — the direct twin of SQL's `NOT EXISTS` — excludes
candidates who share any eligible paper with the source directly. Aggregation,
`HAVING`, ordering and `LIMIT` mirror the SQL exactly.

**Pitfalls.** The subtle one is that "distance exactly two" has *three*
identity exclusions and one existence exclusion, and forgetting any of them
produces answers that look plausible. In particular `?candidate_id !=
?mutual` is easy to omit because it feels implied by the picture — it is not:
nothing stops the second paper from matching with candidate = a different
mutual. Both implementations state all exclusions explicitly. Also note that
on the SQL side multiplicity was collapsed in `eligible_edges`, while on the
SPARQL side several papers can witness the same (source, mutual) hop — the
`COUNT(DISTINCT ?mutual)` makes that difference invisible in the result,
which is what the contract counts anyway (people, not papers).

## Q5 — Cross-area authors through the hierarchy (transitive closure)

*Starting from an ancestor research area, which authors published in at least
N distinct descendant areas?*

This family exists to compare how each model handles *hierarchy*: the
taxonomy from the pipeline document (`computer-science` down to
`database-systems`, `data-mining`, `machine-learning`) with venues assigned
to leaf areas.

**SQL** (`queries/sql/q5.sql`). A recursive CTE `area_closure` computes the
descendant set: base case the ancestor itself, recursive step following
`parent_area_id` downward (this is the walk the `area(parent_area_id)` index
serves). The closure then joins through `venue_area` → `publication` →
`authorship`, with the year filter applied at the publication step, and per
author we count distinct *areas* and distinct publications. Note there is no
venue-set parameter in Q5 — the area closure *is* the venue selection, which
is the point of the family. Threshold `min_distinct_areas`, names last,
deterministic ordering; no LIMIT here (the contract returns all qualifying
authors), so ordering only serves readability of the evidence.

**SPARQL** (`queries/sparql/q5.rq`). The entire recursive CTE collapses into
one line: `?direct_area rdfs:subClassOf* area:{{ancestor_area}}`. The
zero-or-more path includes the ancestor itself, exactly like the closure's
base case. From there the pattern descends `dm:assignedArea` to venues and
onward to publications and authors, with the same aggregates and threshold.
This one-liner-versus-CTE contrast is the clearest expressiveness gap in the
whole workload, and it is the reason the advisor's structural rules route
hierarchy profiles to the graph side ([decision_matrix.md](decision_matrix.md)).

**Pitfalls.** One decision needs to be explicit because it is easy to
misread: the traversal is *stated* in the query (`rdfs:subClassOf*`), not
delegated to an RDFS reasoner configured on the server. Running Fuseki with
inference enabled would have made the comparison depend on an invisible
server toggle, and the materialized entailments would change what "the same
data" even means. With the explicit path, both backends do the transitive
work *inside the measured query*, from identical stored facts. The
`area_count` counts *directly assigned* descendant areas (areas of the venues
the author published in), not every ancestor on the way up — both
implementations agree on this reading, and the contract pins it.

## What "the same query" means here — and what it does not

We matched the queries on *semantics* (frozen contracts, identical inputs,
identical outputs after normalization) and kept each implementation idiomatic
for its language. We did not artificially handicap either side to make the
texts look symmetrical: SQL gets its CTEs and window-free aggregation, SPARQL
gets its property paths and `OPTIONAL`. Where a language genuinely lacks a
capability — SPARQL and path length in Q3 — the workaround is documented,
deterministic, and applied under the same bounds as the other side, rather
than hidden. The measured differences in
[03-benchmark-and-results.md](03-benchmark-and-results.md) should be read
with exactly that framing.
