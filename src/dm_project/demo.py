"""Select and compare correctness-gated live-demo benchmark runs."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import statistics
import sys
import urllib.request
from pathlib import Path
from typing import Any

import psycopg

BACKENDS = ("postgresql", "fuseki")
PROTOCOL_FIELDS = (
    "scale",
    "dataset_sha256",
    "timeout_seconds",
    "warmups",
    "repetitions",
    "execution_order",
)


def select_instances(source: dict[str, Any], tokens: list[str]) -> dict[str, Any]:
    instances = source["instances"]
    known_ids = {instance["id"] for instance in instances}
    families = {instance["profile"] for instance in instances}
    if tokens == ["--all"]:
        return {"instances": instances}

    requested_ids: set[str] = set()
    for token in tokens:
        family = token.upper()
        if family in families:
            requested_ids.update(
                instance["id"] for instance in instances if instance["profile"] == family
            )
        elif token in known_ids:
            requested_ids.add(token)
        else:
            raise ValueError(
                f"unknown family or instance {token!r}; use Q1-Q5, --all, "
                "or an id from config/instances.full.json"
            )
    if not requested_ids:
        raise ValueError("select at least one query family or instance")
    return {
        "instances": [
            instance for instance in instances if instance["id"] in requested_ids
        ]
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _truth(value: Any) -> bool:
    return str(value).lower() == "true"


def _validate_protocol(live: dict[str, Any], accepted: dict[str, Any]) -> None:
    if not live.get("success"):
        raise ValueError("live campaign did not complete successfully")
    if not accepted.get("success"):
        raise ValueError("accepted campaign is not marked successful")
    mismatches = [
        field for field in PROTOCOL_FIELDS if live.get(field) != accepted.get(field)
    ]
    if mismatches:
        details = ", ".join(
            f"{field}: live={live.get(field)!r}, accepted={accepted.get(field)!r}"
            for field in mismatches
        )
        raise ValueError(f"live protocol differs from the accepted campaign: {details}")


def _validate_instances(
    live: dict[str, Any], accepted: dict[str, Any]
) -> list[dict[str, Any]]:
    accepted_by_id = {instance["id"]: instance for instance in accepted["instances"]}
    selected = live["instances"]
    if not selected:
        raise ValueError("live instance selection is empty")
    for instance in selected:
        if accepted_by_id.get(instance["id"]) != instance:
            raise ValueError(
                f"live instance {instance['id']!r} does not match the accepted definition"
            )
    return selected


def _validate_and_group_runs(
    rows: list[dict[str, str]],
    selected: list[dict[str, Any]],
    campaign: dict[str, Any],
) -> dict[tuple[str, str], list[float]]:
    selected_ids = {instance["id"] for instance in selected}
    if {row["instance_id"] for row in rows} != selected_ids:
        raise ValueError("raw benchmark rows do not match the selected instance ids")

    medians: dict[tuple[str, str], list[float]] = {}
    for instance in selected:
        instance_rows = [row for row in rows if row["instance_id"] == instance["id"]]
        if any(not _truth(row["success"]) for row in instance_rows):
            raise ValueError(f"live run contains a failed execution for {instance['id']}")
        signatures = {
            (row["row_count"], row["result_sha256"]) for row in instance_rows
        }
        if len(signatures) != 1:
            raise ValueError(f"result signatures changed within live run {instance['id']}")
        for backend in BACKENDS:
            backend_rows = [row for row in instance_rows if row["backend"] == backend]
            expected = {
                "first": 1,
                "warmup": int(campaign["warmups"]),
                "measured": int(campaign["repetitions"]),
            }
            actual = {
                kind: sum(row["run_kind"] == kind for row in backend_rows)
                for kind in expected
            }
            if actual != expected:
                raise ValueError(
                    f"execution counts differ for {instance['id']} / {backend}: "
                    f"live={actual}, expected={expected}"
                )
            medians[(instance["id"], backend)] = [
                float(row["elapsed_ms"])
                for row in backend_rows
                if row["run_kind"] == "measured"
            ]
    return medians


def compare_runs(
    live_rows: list[dict[str, str]],
    live_campaign: dict[str, Any],
    live_instances: dict[str, Any],
    accepted_summary_rows: list[dict[str, str]],
    accepted_campaign: dict[str, Any],
    accepted_instances: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _validate_protocol(live_campaign, accepted_campaign)
    selected = _validate_instances(live_instances, accepted_instances)
    live_runs = _validate_and_group_runs(live_rows, selected, live_campaign)

    accepted: dict[tuple[str, str], float] = {}
    for row in accepted_summary_rows:
        if (
            row.get("dataset_sha256") == accepted_campaign["dataset_sha256"]
            and row.get("scale") == accepted_campaign["scale"]
            and row.get("correctness_passed") == "true"
            and int(row.get("runs", 0)) == accepted_campaign["repetitions"]
        ):
            accepted[(row["instance_id"], row["backend"])] = float(row["median_ms"])

    comparison: list[dict[str, Any]] = []
    for instance in selected:
        instance_id = instance["id"]
        if any((instance_id, backend) not in accepted for backend in BACKENDS):
            raise ValueError(f"accepted medians are missing for {instance_id}")
        live_pg = statistics.median(live_runs[(instance_id, "postgresql")])
        live_fu = statistics.median(live_runs[(instance_id, "fuseki")])
        accepted_pg = accepted[(instance_id, "postgresql")]
        accepted_fu = accepted[(instance_id, "fuseki")]
        live_winner = "postgresql" if live_pg < live_fu else "fuseki"
        accepted_winner = "postgresql" if accepted_pg < accepted_fu else "fuseki"
        comparison.append(
            {
                "query_family": instance["profile"],
                "instance_id": instance_id,
                "live_postgresql_median_ms": round(live_pg, 3),
                "live_fuseki_median_ms": round(live_fu, 3),
                "accepted_postgresql_median_ms": round(accepted_pg, 3),
                "accepted_fuseki_median_ms": round(accepted_fu, 3),
                "live_winner": live_winner,
                "accepted_winner": accepted_winner,
                "winner_flip": live_winner != accepted_winner,
                "postgresql_live_to_accepted_ratio": round(live_pg / accepted_pg, 3),
                "fuseki_live_to_accepted_ratio": round(live_fu / accepted_fu, 3),
            }
        )
    metadata = {
        "status": "comparable_runtime_replication",
        "authoritative_campaign_replaced": False,
        "instances_compared": len(comparison),
        "winner_flips": sum(row["winner_flip"] for row in comparison),
        "protocol": {field: live_campaign[field] for field in PROTOCOL_FIELDS},
    }
    return comparison, metadata


def _memory_bytes() -> int | None:
    cgroup = Path("/sys/fs/cgroup/memory.max")
    if cgroup.exists():
        value = cgroup.read_text(encoding="utf-8").strip()
        if value != "max":
            return int(value)
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        first = meminfo.read_text(encoding="utf-8").splitlines()[0]
        return int(first.split()[1]) * 1024
    return None


def collect_environment(
    dsn: str,
    fuseki_ping: str,
    runtime_label: str,
    expected_cpus: int,
    expected_memory_gib: float,
) -> dict[str, Any]:
    cpus = os.cpu_count()
    memory_bytes = _memory_bytes()
    memory_gib = memory_bytes / 1024**3 if memory_bytes is not None else None
    if cpus != expected_cpus:
        raise ValueError(f"container sees {cpus} CPUs; expected exactly {expected_cpus}")
    if memory_gib is None or not expected_memory_gib * 0.9 <= memory_gib <= expected_memory_gib * 1.1:
        raise ValueError(
            f"container sees {memory_gib!r} GiB; expected approximately {expected_memory_gib} GiB"
        )
    with psycopg.connect(dsn) as connection:
        postgres_version = connection.execute("SELECT version()").fetchone()[0]
    with urllib.request.urlopen(fuseki_ping, timeout=10) as response:
        fuseki_ping_status = response.status
    return {
        "runtime_label": runtime_label,
        "benchmark_client_placement": "app container on the private Compose network",
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "visible_cpus": cpus,
        "visible_memory_gib": round(memory_gib, 3),
        "expected_cpus": expected_cpus,
        "expected_memory_gib": expected_memory_gib,
        "postgresql_version": postgres_version,
        "fuseki_ping_status": fuseki_ping_status,
    }


def _write_comparison(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _print_comparison(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    print(
        f"{'instance':<30} {'live PG':>10} {'live FU':>10} {'live win':>10} "
        f"{'accepted PG':>12} {'accepted FU':>12} {'accepted win':>12}  result"
    )
    for row in rows:
        result = "WINNER FLIP" if row["winner_flip"] else "same winner"
        print(
            f"{row['instance_id']:<30} "
            f"{row['live_postgresql_median_ms']:>10.1f} "
            f"{row['live_fuseki_median_ms']:>10.1f} "
            f"{row['live_winner']:>10} "
            f"{row['accepted_postgresql_median_ms']:>12.1f} "
            f"{row['accepted_fuseki_median_ms']:>12.1f} "
            f"{row['accepted_winner']:>12}  {result}"
        )
    print(
        f"\n{metadata['instances_compared']} instance(s) compared; "
        f"{metadata['winner_flips']} winner flip(s)."
    )
    print("The accepted campaign remains authoritative; this is a runtime replication.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    select = subparsers.add_parser("select", help="write a frozen instance subset")
    select.add_argument("tokens", nargs="+")
    select.add_argument("--source", type=Path, default=Path("config/instances.full.json"))
    select.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare", help="compare a live run with accepted evidence")
    compare.add_argument("--live-benchmark", type=Path, required=True)
    compare.add_argument("--live-campaign", type=Path, required=True)
    compare.add_argument("--live-instances", type=Path, required=True)
    compare.add_argument("--accepted-summary", type=Path, default=Path("results/final/summary.csv"))
    compare.add_argument("--accepted-campaign", type=Path, default=Path("results/final/campaign.json"))
    compare.add_argument("--accepted-instances", type=Path, default=Path("config/instances.full.json"))
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--metadata-output", type=Path, required=True)

    environment = subparsers.add_parser("environment", help="verify and record container resources")
    environment.add_argument("--dsn", required=True)
    environment.add_argument("--fuseki-ping", required=True)
    environment.add_argument("--runtime-label", default="unspecified")
    environment.add_argument("--expected-cpus", type=int, default=10)
    environment.add_argument("--expected-memory-gib", type=float, default=8.0)
    environment.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    try:
        if args.command == "select":
            selection = select_instances(_read_json(args.source), args.tokens)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
        elif args.command == "compare":
            with args.live_benchmark.open(encoding="utf-8", newline="") as source:
                live_rows = list(csv.DictReader(source))
            with args.accepted_summary.open(encoding="utf-8", newline="") as source:
                accepted_summary = list(csv.DictReader(source))
            rows, metadata = compare_runs(
                live_rows,
                _read_json(args.live_campaign),
                _read_json(args.live_instances),
                accepted_summary,
                _read_json(args.accepted_campaign),
                _read_json(args.accepted_instances),
            )
            _write_comparison(args.output, rows)
            args.metadata_output.write_text(
                json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
            )
            _print_comparison(rows, metadata)
        else:
            evidence = collect_environment(
                args.dsn,
                args.fuseki_ping,
                args.runtime_label,
                args.expected_cpus,
                args.expected_memory_gib,
            )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(evidence, indent=2))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
