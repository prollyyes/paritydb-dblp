# Frozen query and data contracts

These contracts remove the ambiguities listed in Appendix B of the blueprint. Change them only before a benchmark campaign, then commit the change and rerun both backends.

## Canonical data policy

- Stable full DBLP IRIs are identifiers. Names are display values only.
- The input is the pinned June 2026 monthly N-Triples snapshot in `config/dataset.json`; record its SHA-256 in `metadata.json`.
- The subset includes 2005-2024 and the five configured streams. When the pilot limit applies, it allocates an equal quota per venue and selects by a stable SHA-256 of the publication IRI; unused quota is filled from the remaining stable-hash order.
- The relational model has exactly one venue per publication. A publication linked to more than one selected stream is excluded and counted, not assigned arbitrarily.
- `dblp:AmbiguousCreator` resources are excluded and counted. Missing primary names fall back to the final IRI segment and are counted.
- Direct `dblp:authoredBy` links define authorship. They do not expose author order, so `author_position` is null. No transitivity is assigned to direct co-authorship.
- One canonical CSV extract generates both the PostgreSQL load and the RDF graph. This is the data-equivalence boundary.

## Common collaboration edge

For Q2-Q4, two distinct people have one undirected collaboration edge when they share at least one eligible publication. Multiple shared publications never duplicate an edge. Each query applies the same inclusive year interval and venue set before constructing edges.

## Query outputs

### Q1 - Publication trends

Count distinct publications per selected venue and year or decade. A decade starts at `floor(year / 10) * 10`. Empty buckets are omitted. Order by bucket, then venue IRI.

### Q2 - Productive and collaborative authors

For each author, count distinct eligible publications and distinct eligible co-authors. Apply `min_publications` after aggregation. Order by publication count descending, co-author count descending, then person IRI; apply an exact limit without tie expansion.

### Q3 - Bounded collaboration distance

Return the minimum number of collaboration edges from source to target when it is at most `max_depth`; return no row otherwise. A source queried against itself has distance zero. SQL uses a cycle-safe recursive CTE. SPARQL 1.1 property paths can test reachability but cannot expose hop count, so the runner generates exact-depth branches from 1 through `max_depth` and takes the minimum. Intermediate people are pairwise distinct, as every shortest path is simple.

### Q4 - Indirect collaboration discovery

For one source author, return authors at exactly distance two: at least one source-mutual-candidate path exists and no direct source-candidate edge exists. Count distinct mutual co-authors, filter by `min_mutuals`, and order by mutual count descending then candidate IRI.

### Q5 - Hierarchy-aware area analysis

Starting from an ancestor area, follow the area hierarchy to include the area itself and all descendants. For every author, count distinct directly assigned descendant areas and distinct eligible publications. Keep authors meeting `min_distinct_areas`. Both backends receive the same taxonomy; SPARQL states the hierarchy with `rdfs:subClassOf*`, while SQL uses recursive closure. This is explicit hierarchy reasoning, not an unrecorded Fuseki reasoner setting.
