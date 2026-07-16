"""Capture sanitized PostgreSQL load, schema, index, and configuration evidence."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

TABLES = ("venue", "person", "area", "publication", "authorship", "venue_area")
SETTINGS = (
    "shared_buffers",
    "work_mem",
    "effective_cache_size",
    "maintenance_work_mem",
    "max_parallel_workers_per_gather",
    "random_page_cost",
    "effective_io_concurrency",
    "jit",
    "track_io_timing",
    "statement_timeout",
)


def fetch_all(
    connection: psycopg.Connection[Any], query: str, parameters: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, parameters)
        return list(cursor.fetchall())


def csv_count(path: Path) -> int:
    with path.open(encoding="utf-8", newline="") as source:
        return sum(1 for _ in csv.reader(source)) - 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@127.0.0.1:55432/dblp")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    csv_counts = {table: csv_count(args.canonical / f"{table}.csv") for table in TABLES}
    metadata = json.loads((args.canonical / "metadata.json").read_text(encoding="utf-8"))

    with psycopg.connect(args.dsn) as connection:
        version = fetch_all(
            connection,
            "SELECT version() AS version, current_setting('server_version_num') AS version_num",
        )[0]
        table_counts = {
            table: fetch_all(connection, f"SELECT COUNT(*) AS count FROM {table}")[0]["count"]
            for table in TABLES
        }
        table_sizes = fetch_all(
            connection,
            """
            SELECT relname AS table_name,
                   pg_relation_size(oid) AS table_bytes,
                   pg_indexes_size(oid) AS index_bytes,
                   pg_total_relation_size(oid) AS total_bytes
            FROM pg_class
            WHERE relnamespace = 'public'::regnamespace
              AND relkind = 'r'
              AND relname = ANY(%s)
            ORDER BY relname
            """,
            (list(TABLES),),
        )
        columns = fetch_all(
            connection,
            """
            SELECT table_name, ordinal_position, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            (list(TABLES),),
        )
        constraints = fetch_all(
            connection,
            """
            SELECT table_name, constraint_name, constraint_type
            FROM information_schema.table_constraints
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            ORDER BY table_name, constraint_name
            """,
            (list(TABLES),),
        )
        indexes = fetch_all(
            connection,
            """
            SELECT tablename AS table_name, indexname AS index_name, indexdef AS definition
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            ORDER BY tablename, indexname
            """,
            (list(TABLES),),
        )
        settings = fetch_all(
            connection,
            """
            SELECT name, setting, unit, source
            FROM pg_settings
            WHERE name = ANY(%s)
            ORDER BY name
            """,
            (list(SETTINGS),),
        )

    metadata_counts = {
        "publication": metadata["counts"]["publications"],
        "person": metadata["counts"]["persons"],
        "authorship": metadata["counts"]["authorships"],
    }
    payload = {
        "backend": "postgresql",
        "server": version,
        "settings": settings,
        "counts": {
            "postgresql": table_counts,
            "canonical_csv": csv_counts,
            "metadata": metadata_counts,
            "postgresql_matches_csv": table_counts == csv_counts,
            "postgresql_matches_metadata": all(
                table_counts[table] == count for table, count in metadata_counts.items()
            ),
        },
        "table_sizes": table_sizes,
        "schema": {
            "columns": columns,
            "constraints": constraints,
            "indexes": indexes,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not payload["counts"]["postgresql_matches_csv"]:
        raise RuntimeError("PostgreSQL table counts do not match the canonical CSV files")
    if not payload["counts"]["postgresql_matches_metadata"]:
        raise RuntimeError("PostgreSQL counts do not match canonical metadata")


if __name__ == "__main__":
    main()
