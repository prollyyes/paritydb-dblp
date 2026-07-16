# The data pipeline: from a pinned DBLP snapshot to two equivalent stores

This document explains, step by step, how the project turns one official DBLP
RDF snapshot into a PostgreSQL database and a Fuseki graph that contain the
same facts. It covers the decisions we made, the ones we rejected, and the
places where equivalence has to be defended rather than assumed. The companion
documents are [02-query-design.md](02-query-design.md) for the five query
families and [03-benchmark-and-results.md](03-benchmark-and-results.md) for
the experimental protocol and the accepted campaign.

## The idea in one paragraph

We wanted to answer a question that keeps coming up in data management
discussions and is almost always answered with folklore: given the *same*
bibliographic facts, once stored as normalized relations and once as an RDF
graph, which backend is actually the better fit for a given analytical query
profile? Most comparisons we found either used different datasets on each
side, or the same dataset but with silently different semantics (different
deduplication, different entity selection, different type handling), which
makes the timing numbers meaningless. So the core of this project is not the
benchmark itself — it is the machinery that makes the benchmark *fair*: a
single deterministic extract that feeds both stores, frozen query contracts,
a correctness gate that must pass before any timing is recorded, and an
advisor whose rules were written down before we measured anything.

## Why one canonical extract

The earliest design had two independent ingestion paths: parse the DBLP dump
into SQL tables, and separately filter the dump into a smaller N-Triples file
for Fuseki. We abandoned that after realizing every policy decision (which
publications count, what to do with ambiguous authors, how to handle
cross-listed venues) would have to be implemented twice and kept in sync by
hand. Any divergence would silently poison the comparison.

Instead, the pipeline has exactly one place where selection decisions happen:

```text
dblp-2026-06-01.nt.gz  (pinned, MD5-verified)
        |
        v
   dm-extract          <- ALL selection/exclusion policy lives here
        |
        v
 six canonical CSVs + metadata.json
    /           \
   v             v
dm-load-postgres  dm-emit-rdf -> dm-load-fuseki
```

The CSV directory (`data/canonical/`) is the *data-equivalence boundary*.
Everything upstream of it decides what the dataset is; everything downstream
of it is a mechanical change of representation. If the two backends ever
disagree on a query result, the bug is in a query or a loader, never in
entity selection — that property saved us a lot of debugging time.

## Pinning the source

The input is the DBLP monthly RDF/N-Triples release of June 2026, pinned in
`config/dataset.json` by:

- DOI (`10.4230/dblp.rdf.ntriples.2026-06-01`) and landing page,
- the exact download URL,
- the official MD5 published by Dagstuhl.

`dm-extract` refuses to run if the input file's MD5 does not match the pinned
value. There is an escape hatch (`--allow-unverified-source`) that exists only
so the test suite can run against a small fixture graph; it is never used for
real campaigns, and the extractor records in `metadata.json` both the MD5 and
a SHA-256 of whatever it actually read, so any deviation would be visible in
the evidence. We also record a SHA-256 of the *configuration file itself*, so
a campaign can prove which venue list and which policies produced its data.

The compressed dump stays outside Git (it is several gigabytes and
redistributable under CC0 from the source anyway).

## The extractor, pass by pass

`src/dm_project/extract.py` streams the dump with rdflib's strict N-Triples
parser, one line at a time, so memory stays flat regardless of dump size. One
early lesson: the DBLP dump does *not* group all triples of a subject
together, so we could not do a single-pass "read one record, decide, move on"
scan. The extractor instead makes three full passes, each collecting exactly
what the next stage needs:

**Pass 1 — find candidate publications.** We scan for
`dblp:publishedInStream` triples whose object is one of the five configured
streams (SIGMOD, ICDE, PVLDB, KDD, NeurIPS). The result is a map from
publication IRI to the *set* of selected streams it appears in.

**Pass 2 — collect fields for candidates.** For the publications that
survived pass 1 we collect `dblp:yearOfPublication`, `dblp:title` and
`dblp:authoredBy`. Years that fail integer parsing are dropped (treated as
missing), and a publication without a parseable year in range or without a
title is not eligible.

**Pass 3 — resolve creators.** For every author IRI referenced by an eligible
publication we collect `dblp:primaryCreatorName` and check whether the
resource is typed `dblp:AmbiguousCreator`.

### The line prefilters (and why they are safe)

Three full parses of a multi-gigabyte dump is expensive, and profiling showed
almost all the time went into parsing lines we would immediately discard. So
each pass installs a *pure* textual prefilter that may reject a raw line only
if its parsed triple would have been ignored anyway:

- Pass 1 keeps a line only if it literally contains the token
  `<https://dblp.org/rdf/schema#publishedInStream>` — with one exception: any
  line containing a backslash is always parsed, because an N-Triples `\u`
  escape could in principle hide the token from a substring check.
- Passes 2 and 3 keep a line only if the subject IRI (the text between the
  leading `<` and the first `>`) is in the wanted set. Again, anything that
  does not look like a plain IRI subject, or contains an escape before the
  closing `>`, is passed through to the parser unmodified.

The invariant is deliberately conservative: filtered and unfiltered iteration
must see exactly the same triples, and the test suite asserts this on a
fixture graph designed to be adversarial (escapes, blank nodes, odd
whitespace). The prefilters are a speedup, never a semantic change.

### Exclusion policies: excluded and *counted*

Two situations in the raw data have no faithful relational representation,
and we decided early that in both cases the honest move is to exclude the
record and count the exclusion, rather than invent an assignment:

1. **Cross-listed publications.** Our relational schema gives each
   publication exactly one venue (`publication.venue_id` is a single foreign
   key). A publication linked to more than one of the five selected streams
   would force an arbitrary choice, and any choice would leak into Q1 venue
   counts. We exclude those publications entirely — from *both* stores, since
   the exclusion happens before the CSV boundary — and record the count in
   `metadata.json` (`excluded_multiple_selected_venues`).

2. **Ambiguous creators.** DBLP marks resources that aggregate several real
   people as `dblp:AmbiguousCreator`. Keeping them would create fake
   collaboration hubs that distort Q2–Q4 (a single "ambiguous" node can
   connect otherwise distant communities). They are excluded and counted.

Two softer policies follow the same "document it, count it" spirit:

- A creator with no `dblp:primaryCreatorName` falls back to the final segment
  of its IRI as a display name, and the number of fallbacks is recorded.
  Names are display values only; IRIs are the identifiers everywhere.
- Direct `dblp:authoredBy` links carry no author ordering, so
  `author_position` is left empty rather than fabricated. The column exists
  in the schema because the design allows a future switch to DBLP's ordered
  signature resources, but we never pretend to have data we don't.

### Deterministic pilot sampling

For pilot-scale runs, `max_publications` caps the extract (5,000 in the
pilot configuration). Sampling had two requirements: it must be *stratified*,
so no venue dominates the pilot, and it must be *deterministic with no random
seed to lose* — the same input and config must yield the same subset on any
machine, forever.

The scheme: the cap is split into equal per-venue quotas (with the remainder
distributed over the alphabetically first venues). Within each venue,
eligible publications are ranked by the SHA-256 digest of their IRI — a
stable, implementation-independent shuffle — and the quota is taken from the
top. If some venue cannot fill its quota, the shortfall is topped up from the
remaining eligible publications in the same global hash order. There is no
`random()` anywhere in the pipeline. The full-scale configuration
(`config/dataset.full.json`) simply sets `max_publications` to null, which
takes every eligible publication: 42,051 of them for 2005–2024.

### The canonical CSVs

The extract writes six files, matching the relational schema one-to-one:

| File | Contents |
|---|---|
| `venue.csv` | the five streams with label and kind (conference/journal) |
| `publication.csv` | IRI, title, year, single venue |
| `person.csv` | IRI and display name for non-ambiguous creators |
| `authorship.csv` | (publication, person) pairs, position empty |
| `area.csv` | the six-node research-area taxonomy from the config |
| `venue_area.csv` | each venue's single assigned area |

plus `metadata.json` with the source hashes, config hash, policy statements
and all counts. Rows are written in sorted order so the CSVs themselves are
byte-reproducible; two people running the extract on the same dump get
identical files, which we exploited constantly when cross-checking each
other's runs.

### The research-area taxonomy

DBLP has no subject hierarchy, and Q5 needs one. Rather than import an
external taxonomy (with its own versioning and licensing headaches), we
defined a compact hierarchy in the dataset config itself:

```text
computer-science
├── data-management
│   └── database-systems      <- SIGMOD, ICDE, PVLDB
└── artificial-intelligence
    ├── data-mining           <- KDD
    └── machine-learning      <- NeurIPS
```

It is small on purpose. Q5 is about whether each backend can express
*hierarchy-aware* querying (transitive descent from an ancestor), not about
taxonomy scale — and because the taxonomy travels through the same CSV
boundary, both stores are guaranteed the identical hierarchy. On the SQL side
it becomes the self-referencing `area` table; on the RDF side each area is a
`dm:ResearchArea` with `rdfs:subClassOf` links to its parent.

## The relational representation

`sql/schema.sql` defines six tables in third normal form: `person`, `venue`,
`publication`, `authorship`, `area`, `venue_area`. Identifiers are the full
DBLP IRIs as `TEXT` primary keys. We considered surrogate integer keys and
rejected them: the IRIs are what the correctness gate compares across
backends, and an integer mapping layer would have been one more place for the
two representations to drift.

Three indexes exist beyond the primary keys, each motivated by a specific
query family (nothing was added or tuned after measurements began):

- `authorship(person_id)` — the authorship PK is `(publication_id,
  person_id)`, so person-side lookups (every co-author join in Q2–Q4) need
  the reversed access path.
- `publication(venue_id, year)` — exactly the filter pair every query family
  applies first (venue set + year window).
- `area(parent_area_id)` — the descent direction of Q5's recursive closure,
  which walks from parents to children.

`dm-load-postgres` drops and recreates the schema, streams each CSV through
`COPY ... FROM STDIN` in 1 MiB blocks, and finishes with `ANALYZE` so the
planner has fresh statistics before any query is compared. Loads are always
into a fresh database; we never mutate a loaded store.

## The RDF representation

`dm-emit-rdf` regenerates an N-Triples file from the same six CSVs — not from
the original dump. This bears repeating because it is the whole point: the
graph Fuseki serves is a re-serialization of the canonical extract, so it has
exactly the same publications, people and edges as PostgreSQL, including all
exclusions.

Modeling choices:

- We reuse the real DBLP schema vocabulary (`dblp:Publication`,
  `dblp:authoredBy`, `dblp:publishedInStream`, `dblp:primaryCreatorName`,
  `dblp:yearOfPublication`) so the SPARQL queries read like queries against
  actual DBLP, and the resource IRIs are the original DBLP IRIs.
- Years are emitted as `xsd:gYear` typed literals, matching the upstream DBLP
  schema. This is the source of the `xsd:integer(STR(?year))` incantation in
  every SPARQL query — see the query document for why.
- The taxonomy uses a small project namespace (`dm:assignedArea`,
  `dm:ResearchArea`, and `area:` IRIs) plus standard `rdfs:subClassOf` and
  `rdfs:label`, so Q5 can use a plain property path.

The emitter collects triples into a set (deduplicating) and writes them
sorted, so the `.nt` output is byte-deterministic too. `dm-load-fuseki`
replaces the default graph via a Graph Store Protocol `PUT` — replace, not
append, so a reload can never accumulate stale triples.

## The services

`compose.yaml` runs the two backends:

- **PostgreSQL 17** from the official `postgres:17.10-bookworm` image, with a
  healthcheck so loaders don't race the server start.
- **Fuseki 6.1.0** built by `Dockerfile.fuseki` from the official Apache
  distribution archive, with the tarball's SHA-512 verified during the build
  (the same pinning discipline as the dataset). It serves an update-enabled
  *in-memory* dataset at `/dblp` — in-memory was a deliberate choice: at our
  scale (475,002 triples) it removes TDB storage tuning as a confound, and
  the comparison is explicitly scoped to that configuration.

`compose.override.yaml` remaps the PostgreSQL host port for local setups
where 5432 is taken. During Edoardo's isolated validation runs the service was
published at 55432 instead (see his `results/edo/compose.postgres.yaml`
override), which kept his campaign from ever touching a shared instance.

## Where equivalence ends

We claim — and the correctness gate verifies per query — that both stores
answer the frozen query contracts identically. We do *not* claim the
representations are equivalent beyond that boundary. The relational side has
no notion of `rdf:type`; the graph side has no `NOT NULL` constraints. What
is frozen is the *facts* and the *contracts* over them
([query_contracts.md](query_contracts.md)); everything else is each backend
playing to its own model, which is precisely what we want to compare.
