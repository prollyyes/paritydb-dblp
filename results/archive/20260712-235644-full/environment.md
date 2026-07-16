# Experimental environment record

Recorded on 2026-07-12 and re-confirmed at 23:12, immediately before the final
full-scale campaign (pytest 11/11 passing, both containers healthy, AC power
verified after a brief battery interval earlier in the evening; battery at 66%
and charging when the campaign started).

## Hardware and operating system

| Item | Value |
|---|---|
| Machine | MacBook Pro (Mac14,9) |
| Chip | Apple M2 Pro, 10 cores (6 performance + 4 efficiency), arm64 |
| Memory | 16 GB |
| OS | macOS 26.5.1 (build 25F80), Darwin 25.5.0 |
| Power | Connected to AC power, battery 100% |
| Background load | Docker Desktop only; one idle unrelated container (`backend-db-1`, postgres:15) shares the Docker VM; no other significant applications during timing |

## Software versions

| Component | Version |
|---|---|
| Python (project venv) | 3.12.5 |
| psycopg | 3.3.4 |
| rdflib | 7.6.0 |
| Docker Engine | 29.2.1 |
| Docker Compose | v5.0.2 |
| PostgreSQL | 17.10 (Debian 17.10-1.pgdg12+1, image postgres:17.10-bookworm) |
| Apache Jena Fuseki | 6.1.0 (Dockerfile pin), in-memory dataset (`--update --mem /dblp`) |
| Java (Fuseki container) | OpenJDK Temurin 21.0.11 LTS |

## Docker resources

- Docker VM: 10 CPUs, 7.65 GiB memory, no per-container CPU/memory limits configured.
- Project PostgreSQL is published on host port **5434** (host port 5432 was taken by an unrelated container). Port mapping only; the DSN is passed explicitly to every loader/benchmark invocation. No effect on query execution or timing.

## PostgreSQL schema and indexes (sql/schema.sql)

- Primary keys: `person(person_id)`, `venue(venue_id)`, `publication(publication_id)`, `authorship(publication_id, person_id)`, `area(area_id)`, `venue_area(venue_id, area_id)`.
- Secondary indexes: `authorship_person_idx ON authorship(person_id)`, `publication_venue_year_idx ON publication(venue_id, year)`, `area_parent_idx ON area(parent_area_id)`.
- Loader runs `ANALYZE` after each load.

## Timing policy

- Same machine, same 300-second timeout for both backends.
- Per instance and backend: one first execution (doubles as the correctness gate), two warm-ups, five measured repetitions.
- Timing boundary: query execution plus complete result retrieval (fetchall / full SPARQL JSON parse).
- The first execution is reported separately; it is not claimed to be an operating-system cold-cache measurement.
- No chart rendering, copying, or report generation inside the timed section.
