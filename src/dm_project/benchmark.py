"""Correctness-gated benchmark runner for PostgreSQL and Fuseki."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import psycopg
from rdflib import URIRef
from psycopg.rows import dict_row

INTEGER_COLUMNS = {
    "bucket_start", "publication_count", "coauthor_count", "distance",
    "mutual_coauthor_count", "area_count"
}
RESULT_COLUMNS = [
    "query_family", "instance_id", "backend", "run_kind", "run_number",
    "elapsed_ms", "row_count", "result_sha256", "success", "error"
]


def normalize(rows: list[dict[str, Any]]) -> tuple[list[dict[str, str]], str]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        clean: dict[str, str] = {}
        for key, value in row.items():
            if value is None:
                clean[key] = ""
            elif key in INTEGER_COLUMNS:
                clean[key] = str(int(value))
            else:
                clean[key] = str(value)
        normalized.append(clean)
    normalized.sort(key=lambda row: tuple((key, row[key]) for key in sorted(row)))
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return normalized, hashlib.sha256(payload.encode()).hexdigest()


def _venue_ids(parameters: dict[str, Any], dataset: dict[str, Any]) -> list[str]:
    value = parameters.get("venue_ids")
    return [venue["id"] for venue in dataset["venues"]] if value == "all" else list(value)


def render_sparql(template: str, parameters: dict[str, Any], dataset: dict[str, Any]) -> str:
    replacements = {key: str(value) for key, value in parameters.items() if key != "venue_ids"}
    if "venue_ids" in parameters:
        replacements["venue_values"] = " ".join(URIRef(value).n3() for value in _venue_ids(parameters, dataset))
    if "ancestor_area" in replacements and not re.fullmatch(r"[a-z0-9-]+", replacements["ancestor_area"]):
        raise ValueError("ancestor_area must contain only lowercase letters, digits, and hyphens")
    if "path_branches" in template:
        replacements["path_branches"] = build_path_branches(parameters, replacements["venue_values"])
    for key, value in replacements.items():
        template = template.replace("{{" + key + "}}", value)
    missing = sorted(set(re.findall(r"{{([a-z_]+)}}", template)))
    if missing:
        raise ValueError(f"missing SPARQL template parameters: {', '.join(missing)}")
    return template


def build_path_branches(parameters: dict[str, Any], venue_values: str) -> str:
    source = URIRef(parameters["source_id"]).n3()
    target = URIRef(parameters["target_id"]).n3()
    if source == target:
        return "BIND(0 AS ?candidate_distance)"
    year_from, year_to = int(parameters["year_from"]), int(parameters["year_to"])
    branches: list[str] = []
    for depth in range(1, int(parameters["max_depth"]) + 1):
        lines = ["{", f"  BIND({source} AS ?node0)", f"  BIND({target} AS ?node{depth})"]
        for edge in range(1, depth + 1):
            lines.extend([
                f"  VALUES ?venue{edge} {{ {venue_values} }}",
                f"  ?paper{edge} dblp:publishedInStream ?venue{edge} ;",
                f"          dblp:yearOfPublication ?year{edge} ;",
                f"          dblp:authoredBy ?node{edge - 1}, ?node{edge} .",
                f"  FILTER(xsd:integer(STR(?year{edge})) >= {year_from} && xsd:integer(STR(?year{edge})) <= {year_to})",
                f"  FILTER(?node{edge - 1} != ?node{edge})",
            ])
        distinct = [f"?node{i} != ?node{j}" for i in range(depth + 1) for j in range(i + 1, depth + 1)]
        lines.extend([f"  FILTER({' && '.join(distinct)})", f"  BIND({depth} AS ?candidate_distance)", "}"])
        branches.append("\n".join(lines))
    return "\nUNION\n".join(branches)


def _postgres_runner(connection: psycopg.Connection[Any], query: str, parameters: dict[str, Any]) -> Callable[[], list[dict[str, Any]]]:
    def run() -> list[dict[str, Any]]:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, parameters)
            return list(cursor.fetchall())
    return run


def _fuseki_runner(endpoint: str, query: str, timeout_seconds: int) -> Callable[[], list[dict[str, Any]]]:
    def run() -> list[dict[str, Any]]:
        body = urllib.parse.urlencode({"query": query}).encode()
        request = urllib.request.Request(endpoint, data=body, headers={"Accept": "application/sparql-results+json"})
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            data = json.load(response)
        return [{key: binding.get("value") for key, binding in row.items()} for row in data["results"]["bindings"]]
    return run


def _execute(run: Callable[[], list[dict[str, Any]]]) -> tuple[float, int, str]:
    started = time.perf_counter_ns()
    rows = run()
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000
    normalized, digest = normalize(rows)
    return elapsed_ms, len(normalized), digest


def _record(profile: str, instance_id: str, backend: str, kind: str, number: int, run: Callable[[], list[dict[str, Any]]]) -> dict[str, Any]:
    try:
        elapsed, count, digest = _execute(run)
        return dict(zip(RESULT_COLUMNS, [profile, instance_id, backend, kind, number, f"{elapsed:.3f}", count, digest, True, ""]))
    except Exception as exc:
        return dict(zip(RESULT_COLUMNS, [profile, instance_id, backend, kind, number, "", 0, "", False, str(exc)]))


def execution_schedule(
    warmups: int,
    repetitions: int,
    policy: str,
    instance_index: int,
) -> list[tuple[str, int, str]]:
    """Return the deterministic backend order outside the timed query boundary."""
    if policy == "blocked":
        return [
            (kind, number, backend)
            for backend in ("postgresql", "fuseki")
            for kind, count in (("warmup", warmups), ("measured", repetitions))
            for number in range(1, count + 1)
        ]
    schedule: list[tuple[str, int, str]] = []
    for kind, count in (("warmup", warmups), ("measured", repetitions)):
        for number in range(1, count + 1):
            order = ("postgresql", "fuseki")
            if (instance_index + number) % 2:
                order = tuple(reversed(order))
            schedule.extend((kind, number, backend) for backend in order)
    return schedule


def _progress(path: Path | None, event: str, **details: Any) -> None:
    record = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **details,
    }
    print(json.dumps(record, sort_keys=True), flush=True)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as target:
            target.write(json.dumps(record, sort_keys=True) + "\n")


def correctness_matches(checks: dict[str, dict[str, Any]]) -> bool:
    return (
        checks["postgresql"]["row_count"] == checks["fuseki"]["row_count"]
        and checks["postgresql"]["result_sha256"]
        == checks["fuseki"]["result_sha256"]
    )


def benchmark(args: argparse.Namespace) -> None:
    dataset_bytes = args.dataset.read_bytes()
    dataset_digest = hashlib.sha256(dataset_bytes).hexdigest()
    dataset = json.loads(dataset_bytes)
    instances = json.loads(args.instances.read_text(encoding="utf-8"))["instances"]
    enabled_instances = [instance for instance in instances if instance.get("enabled", True)]
    records: list[dict[str, Any]] = []
    failure: str | None = None
    if args.progress_log is not None:
        args.progress_log.parent.mkdir(parents=True, exist_ok=True)
        args.progress_log.write_text("", encoding="utf-8")
    _progress(
        args.progress_log,
        "campaign_started",
        instances=len(enabled_instances),
        execution_order=args.execution_order,
    )
    with psycopg.connect(args.dsn) as connection:
        connection.execute("SELECT set_config('statement_timeout', %s, false)", (f"{args.timeout_seconds}s",))
        enabled_ordinal = 0
        for instance_index, instance in enumerate(instances):
            if not instance.get("enabled", True):
                continue
            enabled_ordinal += 1
            ordinal = enabled_ordinal
            _progress(
                args.progress_log,
                "instance_started",
                instance_id=instance["id"],
                profile=instance["profile"],
                ordinal=ordinal,
                total=len(enabled_instances),
            )
            profile = instance["profile"]
            params = dict(instance["parameters"])
            params["venue_ids"] = _venue_ids(params, dataset) if "venue_ids" in params else None
            sql_query = (args.query_dir / "sql" / f"{profile.lower()}.sql").read_text(encoding="utf-8")
            sparql_template = (args.query_dir / "sparql" / f"{profile.lower()}.rq").read_text(encoding="utf-8")
            sparql_query = render_sparql(sparql_template, instance["parameters"], dataset)
            runners = {
                "postgresql": _postgres_runner(connection, sql_query, params),
                "fuseki": _fuseki_runner(args.fuseki_endpoint, sparql_query, args.timeout_seconds),
            }
            # These are the actual first executions as well as the correctness gate;
            # no hidden query warms either backend before them.
            first_order = ("postgresql", "fuseki")
            if args.execution_order == "interleaved" and instance_index % 2:
                first_order = tuple(reversed(first_order))
            checks = {}
            for backend in first_order:
                checks[backend] = _record(
                    profile, instance["id"], backend, "first", 1, runners[backend]
                )
                records.append(checks[backend])
            if any(not row["success"] for row in checks.values()):
                failure = f"first/correctness execution failed for {instance['id']}"
                _progress(
                    args.progress_log,
                    "instance_failed",
                    instance_id=instance["id"],
                    reason=failure,
                )
                break
            if not correctness_matches(checks):
                failure = f"correctness gate failed for {instance['id']}"
                _progress(
                    args.progress_log,
                    "instance_failed",
                    instance_id=instance["id"],
                    reason=failure,
                )
                break
            schedule = execution_schedule(
                args.warmups, args.repetitions, args.execution_order, instance_index
            )
            for kind, number, backend in schedule:
                records.append(
                    _record(
                        profile,
                        instance["id"],
                        backend,
                        kind,
                        number,
                        runners[backend],
                    )
                )
            if any(not row["success"] for row in records if row["instance_id"] == instance["id"]):
                failure = f"timed execution failed for {instance['id']}"
                _progress(
                    args.progress_log,
                    "instance_failed",
                    instance_id=instance["id"],
                    reason=failure,
                )
                break
            _progress(
                args.progress_log,
                "instance_completed",
                instance_id=instance["id"],
                ordinal=ordinal,
                total=len(enabled_instances),
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=RESULT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    write_summary(records, args.output.with_name("summary.csv"), args.scale, dataset_digest, args.repetitions)
    campaign = {
        "scale": args.scale,
        "dataset_sha256": dataset_digest,
        "instances_sha256": hashlib.sha256(args.instances.read_bytes()).hexdigest(),
        "timeout_seconds": args.timeout_seconds,
        "warmups": args.warmups,
        "repetitions": args.repetitions,
        "execution_order": args.execution_order,
        "success": failure is None,
        "failure": failure,
    }
    args.output.with_name("campaign.json").write_text(json.dumps(campaign, indent=2) + "\n", encoding="utf-8")
    _progress(
        args.progress_log,
        "campaign_completed" if failure is None else "campaign_failed",
        success=failure is None,
        failure=failure,
        rows=len(records),
    )
    if failure:
        raise RuntimeError(failure)


def write_summary(records: list[dict[str, Any]], path: Path, scale: str, dataset_digest: str, repetitions: int) -> None:
    groups: dict[tuple[str, str, str], list[float]] = {}
    for row in records:
        if row["run_kind"] == "measured" and row["success"]:
            groups.setdefault((row["query_family"], row["instance_id"], row["backend"]), []).append(float(row["elapsed_ms"]))
    with path.open("w", encoding="utf-8", newline="") as target:
        fields = [
            "query_family", "instance_id", "backend", "scale", "dataset_sha256",
            "correctness_passed", "median_ms", "min_ms", "max_ms", "runs"
        ]
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for (profile, instance, backend), values in sorted(groups.items()):
            if len(values) != repetitions:
                continue
            writer.writerow({
                "query_family": profile, "instance_id": instance, "backend": backend,
                "scale": scale, "dataset_sha256": dataset_digest, "correctness_passed": "true",
                "median_ms": f"{statistics.median(values):.3f}", "min_ms": f"{min(values):.3f}",
                "max_ms": f"{max(values):.3f}", "runs": len(values),
            })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@localhost:5432/dblp")
    parser.add_argument("--fuseki-endpoint", default="http://localhost:3030/dblp/query")
    parser.add_argument("--dataset", type=Path, default=Path("config/dataset.json"))
    parser.add_argument("--instances", type=Path, default=Path("config/instances.json"))
    parser.add_argument("--query-dir", type=Path, default=Path("queries"))
    parser.add_argument("--output", type=Path, default=Path("results/benchmark.csv"))
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument(
        "--execution-order",
        choices=("blocked", "interleaved"),
        default="blocked",
        help="backend scheduling policy; interleaved alternates the backend run order",
    )
    parser.add_argument(
        "--progress-log",
        type=Path,
        help="optional UTC instance progress log written outside timed query execution",
    )
    parser.add_argument("--scale", default="pilot", help="dataset scale label recorded in campaign evidence")
    args = parser.parse_args()
    if args.repetitions < 5:
        parser.error("at least five measured repetitions are required")
    benchmark(args)


if __name__ == "__main__":
    main()
