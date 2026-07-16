# Benchmark environment

Captured on 2026-07-13 before the campaign.

## Host

- Machine: MacBook Pro, model identifier Mac14,9.
- Processor: Apple M2 Pro, 10 cores (6 performance, 4 efficiency).
- Memory: 16 GB.
- Architecture: arm64.
- Operating system: macOS 26.5, build 25F71.
- Kernel: Darwin 25.5.0.
- Power state: AC power attached; battery at 80% when preflight evidence was captured.
- Free host disk at preflight: 22 GiB.

Serial numbers, hardware UUIDs, and device identifiers are intentionally omitted.

## Python environment

- Conda: 25.5.1.
- Environment: `data_management`.
- Python: 3.12.13.
- psycopg: 3.3.4.
- psycopg-binary: 3.3.4.
- RDFLib: 7.6.0.
- pytest: 8.4.2.
- Project baseline commit: `bd4d5cd2e4161162a4ef7586fef9ceb4bf28d944`.

## Container runtime

- Colima: 0.8.1 using macOS Virtualization.Framework and Docker runtime.
- Colima allocation: 6 virtual CPUs, 8 GB memory.
- Docker client: 28.0.2.
- Docker server: 27.4.0.
- Docker storage driver: overlay2.
- Docker Compose: 2.34.0.

## PostgreSQL service

- PostgreSQL: 17.10, Debian package `17.10-1.pgdg12+1`, arm64.
- PostgreSQL endpoint: `127.0.0.1:55432`, database `dblp`. The non-default host port avoids ambiguity with an existing local PostgreSQL listener on 5432.

No explicit Docker CPU or memory limit is applied to PostgreSQL; it runs within the shared Colima allocation.

## Timing conditions

- One machine and one Colima session are used for all PostgreSQL measurements.
- The machine remains connected to AC power.
- The benchmark includes complete query execution and result retrieval.
- PostgreSQL uses one fixed statement timeout for all Q1-Q3 runs.
- The first execution is reported separately and is not described as an operating-system cold-cache result.
- Two warm-ups and at least five measured repetitions are required per PostgreSQL instance.
