# Controlled final campaign environment

Captured on 2026-07-14 immediately before the paired campaign.

## Host and runtime

- MacBook Pro (Mac14,9), Apple M2 Pro, 10 cores (6 performance and 4
  efficiency), 16 GB RAM, arm64.
- macOS 26.5 (build 25F71), Darwin 25.5.0.
- AC power attached; battery 76% at preflight.
- Colima 0.8.1 using macOS Virtualization.Framework (`vz`), ARM64, Docker
  runtime, exactly 10 vCPUs, 8 GiB memory, and 100 GiB virtual disk.
- Docker client 28.0.2 and server 27.4.0, overlay2 storage.
- No per-container CPU, memory, or cpuset limits. Only the two project
  containers were running during timing.

## Project software

- Conda 25.5.1; `data_management`; Python 3.12.13.
- PostgreSQL 17.10 (`postgres:17.10-bookworm`), published at
  `127.0.0.1:55432`.
- Apache Jena Fuseki 6.1.0 with an in-memory `/dblp` dataset, OpenJDK Temurin
  21.0.11 LTS, published at `127.0.0.1:3030`. Fuseki reported a 4.0 GiB JVM
  memory limit.
- The cached ARM64 Fuseki image was reused after its server binary reported
  version 6.1.0; Docker buildx was unavailable and no image contents changed.
- Matplotlib 3.11.0 was installed only after the timed campaign to regenerate
  figures from the accepted CSV evidence; it was not present during timing.

## PostgreSQL configuration

- `shared_buffers`: 128 MiB; `work_mem`: 4 MiB; `effective_cache_size`: 4 GiB.
- `max_parallel_workers_per_gather`: 2; JIT enabled; `random_page_cost`: 4.
- Schema and indexes are exactly those in `sql/schema.sql`; the loader ran
  `ANALYZE` after the clean load.

## Timing policy

- One first/correctness execution, two warm-ups, and five measured repetitions
  per backend and instance.
- Interleaved, deterministically alternating backend order.
- Query execution, complete result retrieval, and normalization are timed.
- Fixed 300-second timeout; plans and evaluation are outside timed runs.
