"""Create the PostgreSQL schema and bulk-load canonical CSV files."""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

TABLES = ("venue", "person", "area", "publication", "authorship", "venue_area")


def load(dsn: str, canonical_dir: Path, schema_path: Path) -> None:
    with psycopg.connect(dsn) as connection:
        connection.execute(schema_path.read_text(encoding="utf-8"))
        for table in TABLES:
            csv_path = canonical_dir / f"{table}.csv"
            with connection.cursor() as cursor, csv_path.open("rb") as source:
                with cursor.copy(f"COPY {table} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
                    while block := source.read(1024 * 1024):
                        copy.write(block)
        connection.execute("ANALYZE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@localhost:5432/dblp")
    parser.add_argument("--canonical", type=Path, default=Path("data/canonical"))
    parser.add_argument("--schema", type=Path, default=Path("sql/schema.sql"))
    args = parser.parse_args()
    load(args.dsn, args.canonical, args.schema)
    print("PostgreSQL load complete")


if __name__ == "__main__":
    main()

