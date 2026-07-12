# ParityDB-DBLP

### An explainable SQL-SPARQL comparison over bibliographic knowledge graphs

ParityDB-DBLP is a reproducible data-management study comparing PostgreSQL/SQL and Apache Jena Fuseki/SPARQL over semantically equivalent representations of a curated DBLP subset. The project evaluates correctness, query expressiveness, readability, and execution performance across relational aggregation, collaboration analysis, bounded graph traversal, and hierarchy-aware querying.

Its final component is an explainable query-routing advisor: given a declared workload profile, it recommends a backend, states the structural reason, and connects the recommendation to correctness-gated benchmark evidence.

## Research question

When the same bibliographic facts are represented as normalized relations and as an RDF graph, which backend is the more suitable choice for a particular analytical query profile?

The project treats this as a controlled comparison rather than a universal ranking. Every conclusion is scoped to the selected DBLP snapshot, schemas, indexes, software versions, machine, and experimental protocol.

## Architecture

```text
Pinned DBLP N-Triples snapshot
             |
             v
  Deterministic canonical extract
        /                 \
       v                   v
PostgreSQL tables     Canonical RDF graph
       |                   |
      SQL                SPARQL
        \                 /
         correctness gate
                |
                v
       paired benchmark evidence
                |
                v
      explainable routing advisor
```

One canonical CSV extract feeds both backend representations. This makes entity selection, exclusions, identifiers, and taxonomy enrichment identical before any query is compared.

## Dataset and scope

- Source: DBLP monthly RDF/N-Triples snapshot of June 2026, DOI `10.4230/dblp.rdf.ntriples.2026-06-01`.
- Time window: 2005-2024.
- Publication streams: SIGMOD, ICDE, PVLDB, KDD, and NeurIPS.
- Pilot ceiling: 5,000 publications, stratified across venues and selected through a stable hash of each publication IRI.
- Backends: PostgreSQL 17 and Apache Jena Fuseki 6.1.
- Semantic enrichment: a compact research-area hierarchy represented equivalently in SQL and RDF.

The exact inclusion, exclusion, collaboration, and result-equivalence rules are frozen in [`docs/query_contracts.md`](docs/query_contracts.md).

## Query workload

| Family | Analytical question | Principal feature |
|---|---|---|
| Q1 | Publication trends by venue and period | Grouping and aggregation |
| Q2 | Productive authors and distinct co-author counts | Aggregation and self-join |
| Q3 | Bounded shortest collaboration distance | Recursive traversal |
| Q4 | Indirect collaborator discovery | Exact two-hop graph pattern |
| Q5 | Cross-area authors through a category hierarchy | Recursive closure / RDFS path |

Each family has paired SQL and SPARQL implementations under [`queries/`](queries/). Result identifiers and typed values are normalized before comparison.

## Reproducibility safeguards

- The source snapshot is pinned by DOI, download URL, and official MD5.
- The extractor records MD5, SHA-256, configuration hash, venue list, selection policy, exclusions, and output counts.
- Cross-listed publications and ambiguous creator resources follow explicit documented rules.
- PostgreSQL CSV and RDF outputs are derived from the same canonical facts.
- Benchmark timing begins only after the first paired results pass a SHA-256 correctness gate.
- PostgreSQL and Fuseki use the same timeout and result-retrieval boundary.
- Campaign metadata records scale, configuration fingerprints, timeout, repetitions, and completion status.
- Advisor evidence must match the query family, instance, dataset fingerprint, scale, and minimum successful run count.

## Environment

Conda and Docker are expected. Create the Python environment and start the two services with:

```bash
conda env create -f environment.yml
conda activate data_management
docker compose up -d --build
```

The local Compose stack exposes PostgreSQL at `localhost:5432` and an update-enabled, in-memory Fuseki dataset at `localhost:3030/dblp`.

## Build the equivalent datasets

Download the pinned snapshot from the DOI landing page and keep the compressed data outside Git. Then run:

```bash
dm-extract /path/to/dblp-2026-06-01.nt.gz
dm-emit-rdf
dm-load-postgres
dm-load-fuseki
```

The PostgreSQL loader recreates the six project tables. The Fuseki loader replaces the default graph. Both commands are intended for isolated project datasets.

## Configure benchmark instances

```bash
cp config/instances.example.json config/instances.json
```

Set representative DBLP person IRIs for Q3 and Q4, enable the instances, and add parameter variations while keeping the five query contracts unchanged.

## Run the benchmark

```bash
dm-benchmark --instances config/instances.json
```

Outputs:

- `results/benchmark.csv`: raw first, warm-up, and measured executions.
- `results/summary.csv`: complete median, minimum, and maximum timings.
- `results/campaign.json`: provenance, configuration fingerprints, and campaign status.

The first execution on each backend is also the correctness check. A mismatch or execution failure is logged and stops the campaign before evidence can reach the advisor.

## Use the advisor

```bash
dm-advisor Q3 --scale pilot --instance q3_connected
```

The structural policy is defined in [`config/profiles.json`](config/profiles.json) and documented in [`docs/decision_matrix.md`](docs/decision_matrix.md). Recommendations remain distinct from measured winners, allowing exceptions and latency regret to be reported directly.

## Verification

```bash
pytest
```

The test suite covers deterministic extraction, source verification, exclusion policies, RDF generation, SPARQL parsing and execution, bounded path generation, result normalization, and advisor evidence handling.

## Repository structure

- `config/` - pinned dataset definition, query profiles, and instance template.
- `src/dm_project/` - extractor, emitters, loaders, benchmark, and advisor.
- `sql/schema.sql` - normalized relational schema and workload indexes.
- `queries/sql/` and `queries/sparql/` - paired query implementations.
- `docs/` - frozen query contracts and routing decision matrix.
- `tests/fixtures/` - adversarial DBLP-style test graph.
- `results/` - benchmark output location.

## Authors

- Luca Tam
- Edoardo Simonetti Spallotta

Developed for the Data Management course, academic year 2025/2026.

## License

The software is released under the MIT License. DBLP data is distributed separately under CC0 1.0.

