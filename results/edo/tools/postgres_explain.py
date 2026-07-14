"""Capture PostgreSQL Q1-Q3 execution plans outside benchmark timing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import psycopg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@127.0.0.1:55432/dblp")
    parser.add_argument("--dataset", type=Path, default=Path("config/dataset.json"))
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--query-dir", type=Path, default=Path("queries/sql"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    all_venues = [venue["id"] for venue in dataset["venues"]]
    instances = json.loads(args.instances.read_text(encoding="utf-8"))["instances"]
    enabled = [instance for instance in instances if instance.get("enabled", True)]
    unsupported = sorted({instance["profile"] for instance in enabled} - {"Q1", "Q2", "Q3"})
    if unsupported:
        parser.error(f"PostgreSQL plan collector accepts Q1-Q3 only: {', '.join(unsupported)}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
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
            with connection.cursor() as cursor:
                cursor.execute(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query,
                    parameters,
                )
                plan = cursor.fetchone()[0]
            output_path = args.output_dir / f"{instance['id']}.json"
            payload = {
                "backend": "postgresql",
                "query_family": profile,
                "instance_id": instance["id"],
                "parameters": instance["parameters"],
                "plan": plan,
            }
            output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            manifest.append(
                {
                    "query_family": profile,
                    "instance_id": instance["id"],
                    "file": output_path.name,
                    "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
                }
            )
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
