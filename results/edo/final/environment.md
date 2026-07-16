# PostgreSQL final-scale environment

Captured immediately before the PostgreSQL-only Q1-Q3 campaign on 2026-07-14 at 11:59 CEST.

## Host

- Machine: MacBook Pro (Mac14,9), Apple M2 Pro, 10 CPU cores (6 performance and 4 efficiency).
- Memory: 16 GB; architecture: arm64.
- Operating system: macOS 26.5 (build 25F71), Darwin 25.5.0.
- Power: AC attached; battery 76%.
- Available host disk space: 19 GiB. This is a recorded resource constraint; no generated dataset or database storage is committed to Git.

## Python and project baseline

- Conda: 25.5.1; environment: `data_management`.
- Python: 3.12.13; psycopg: 3.3.4; RDFLib: 7.6.0; pytest: 8.4.2.
- Baseline commit: `bd4d5cd2e4161162a4ef7586fef9ceb4bf28d944`.

## Container runtime and PostgreSQL

- Colima 0.8.1, macOS Virtualization.Framework, Docker runtime, arm64.
- Colima allocation: 6 vCPUs, 8 GiB memory, 100 GiB disk.
- Docker client 28.0.2; Docker server 27.4.0; storage driver: overlay2.
- PostgreSQL 17.10 (Debian `17.10-1.pgdg12+1`, arm64), database `dblp`.
- Endpoint: `127.0.0.1:55432`; this explicit port is used in every PostgreSQL command.
- The PostgreSQL container has no explicit CPU or memory limit and runs within the shared Colima allocation.

The Docker Compose plugin was unavailable in this environment. Its guide-required service-health check was performed equivalently with `docker ps`; `final_proj-postgres-1` was healthy before timing. Fuseki was not started or inspected for this Edoardo-only campaign.

## Timing policy

- Fixed full canonical dataset and frozen `instances.json`.
- Statement timeout: 300 seconds.
- One first execution, two warm-ups, and five measured repetitions per Q1-Q3 instance.
- Timing includes execution and complete result retrieval.
- Execution plans are captured separately after timing and are not timing measurements.
- The first execution is reported as the first observed execution in this session, not as an operating-system cold-cache measurement.
