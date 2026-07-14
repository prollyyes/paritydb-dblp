"""Run and archive PostgreSQL-only Q1-Q3 measurements."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from dm_project.benchmark import normalize

RAW_COLUMNS = [
    "query_family",
    "instance_id",
    "backend",
    "run_kind",
    "run_number",
    "elapsed_ms",
    "row_count",
    "result_sha256",
    "success",
    "error",
]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_query(
    connection: psycopg.Connection[Any], query: str, parameters: dict[str, Any]
) -> tuple[float, int, str]:
    started = time.perf_counter_ns()
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, parameters)
        rows = list(cursor.fetchall())
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    normalized, digest = normalize(rows)
    return elapsed_ms, len(normalized), digest


def record_run(
    connection: psycopg.Connection[Any],
    profile: str,
    instance_id: str,
    kind: str,
    number: int,
    query: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    try:
        elapsed_ms, row_count, digest = run_query(connection, query, parameters)
        values = [
            profile,
            instance_id,
            "postgresql",
            kind,
            number,
            f"{elapsed_ms:.3f}",
            row_count,
            digest,
            True,
            "",
        ]
    except Exception as exc:
        values = [profile, instance_id, "postgresql", kind, number, "", 0, "", False, str(exc)]
    return dict(zip(RAW_COLUMNS, values))


def write_raw(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=RAW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)


def write_summary(path: Path, records: list[dict[str, Any]], repetitions: int) -> None:
    fields = [
        "query_family",
        "instance_id",
        "backend",
        "first_ms",
        "median_ms",
        "min_ms",
        "max_ms",
        "measured_runs",
        "row_count",
        "result_sha256",
    ]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        groups.setdefault((record["query_family"], record["instance_id"]), []).append(record)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for (profile, instance_id), group in sorted(groups.items()):
            first = next(row for row in group if row["run_kind"] == "first")
            measured = [row for row in group if row["run_kind"] == "measured" and row["success"]]
            if len(measured) != repetitions:
                continue
            elapsed = [float(row["elapsed_ms"]) for row in measured]
            writer.writerow(
                {
                    "query_family": profile,
                    "instance_id": instance_id,
                    "backend": "postgresql",
                    "first_ms": first["elapsed_ms"],
                    "median_ms": f"{statistics.median(elapsed):.3f}",
                    "min_ms": f"{min(elapsed):.3f}",
                    "max_ms": f"{max(elapsed):.3f}",
                    "measured_runs": len(measured),
                    "row_count": first["row_count"],
                    "result_sha256": first["result_sha256"],
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@127.0.0.1:55432/dblp")
    parser.add_argument("--dataset", type=Path, default=Path("config/dataset.json"))
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--query-dir", type=Path, default=Path("queries/sql"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--scale", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    if args.repetitions < 5:
        parser.error("at least five measured repetitions are required")

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    all_venues = [venue["id"] for venue in dataset["venues"]]
    instances = json.loads(args.instances.read_text(encoding="utf-8"))["instances"]
    enabled = [instance for instance in instances if instance.get("enabled", True)]
    unsupported = sorted({instance["profile"] for instance in enabled} - {"Q1", "Q2", "Q3"})
    if unsupported:
        parser.error(f"PostgreSQL evidence runner accepts Q1-Q3 only: {', '.join(unsupported)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    failure: str | None = None
    with psycopg.connect(args.dsn) as connection:
        connection.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            (f"{args.timeout_seconds}s",),
        )
        for instance in enabled:
            profile = instance["profile"]
            query = (args.query_dir / f"{profile.lower()}.sql").read_text(encoding="utf-8")
            parameters = dict(instance["parameters"])
            if parameters.get("venue_ids") == "all":
                parameters["venue_ids"] = all_venues

            records.append(
                record_run(connection, profile, instance["id"], "first", 1, query, parameters)
            )
            if not records[-1]["success"]:
                failure = f"first execution failed for {instance['id']}"
                break
            for number in range(1, args.warmups + 1):
                records.append(
                    record_run(connection, profile, instance["id"], "warmup", number, query, parameters)
                )
            for number in range(1, args.repetitions + 1):
                records.append(
                    record_run(connection, profile, instance["id"], "measured", number, query, parameters)
                )
            group = [record for record in records if record["instance_id"] == instance["id"]]
            if any(not record["success"] for record in group):
                failure = f"execution failed for {instance['id']}"
                break
            hashes = {record["result_sha256"] for record in group}
            if len(hashes) != 1:
                failure = f"result instability detected for {instance['id']}"
                break

    write_raw(args.output_dir / "benchmark.csv", records)
    write_summary(args.output_dir / "summary.csv", records, args.repetitions)
    campaign = {
        "backend": "postgresql",
        "scope": ["Q1", "Q2", "Q3"],
        "scale": args.scale,
        "dataset_sha256": file_sha256(args.dataset),
        "instances_sha256": file_sha256(args.instances),
        "query_sha256": {
            profile: file_sha256(args.query_dir / f"{profile.lower()}.sql")
            for profile in ("Q1", "Q2", "Q3")
        },
        "timeout_seconds": args.timeout_seconds,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "success": failure is None,
        "failure": failure,
    }
    (args.output_dir / "campaign.json").write_text(
        json.dumps(campaign, indent=2) + "\n", encoding="utf-8"
    )
    if failure:
        raise RuntimeError(failure)


if __name__ == "__main__":
    main()
