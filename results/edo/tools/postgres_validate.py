"""Independently validate PostgreSQL Q1-Q3 semantics and archive the checks."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from dm_project.benchmark import normalize


def execute(
    connection: psycopg.Connection[Any], query: str, parameters: dict[str, Any]
) -> list[dict[str, Any]]:
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, parameters)
        return list(cursor.fetchall())


def validate_q1(
    connection: psycopg.Connection[Any], rows: list[dict[str, Any]], parameters: dict[str, Any]
) -> dict[str, Any]:
    publications = execute(
        connection,
        """
        SELECT publication_id, venue_id, year
        FROM publication
        WHERE year BETWEEN %(year_from)s AND %(year_to)s
          AND venue_id = ANY(%(venue_ids)s)
        """,
        parameters,
    )
    reference: dict[tuple[str, int], int] = defaultdict(int)
    for publication in publications:
        year = int(publication["year"])
        bucket = (year // 10) * 10 if parameters["bucket"] == "decade" else year
        reference[(publication["venue_id"], bucket)] += 1
    observed = {
        (row["venue_id"], int(row["bucket_start"])): int(row["publication_count"])
        for row in rows
    }
    keys_are_unique = len(observed) == len(rows)
    return {
        "passed": observed == reference and keys_are_unique,
        "observed_publications": sum(observed.values()),
        "reference_publications": len(publications),
        "observed_groups": len(observed),
        "reference_groups": len(reference),
        "unique_venue_bucket_keys": keys_are_unique,
    }


def validate_q2(
    connection: psycopg.Connection[Any], rows: list[dict[str, Any]], parameters: dict[str, Any]
) -> dict[str, Any]:
    authorships = execute(
        connection,
        """
        SELECT a.publication_id, a.person_id
        FROM authorship AS a
        JOIN publication AS publication USING (publication_id)
        WHERE publication.year BETWEEN %(year_from)s AND %(year_to)s
          AND publication.venue_id = ANY(%(venue_ids)s)
        """,
        parameters,
    )
    publication_authors: dict[str, set[str]] = defaultdict(set)
    author_publications: dict[str, set[str]] = defaultdict(set)
    for authorship in authorships:
        publication_id = authorship["publication_id"]
        person_id = authorship["person_id"]
        publication_authors[publication_id].add(person_id)
        author_publications[person_id].add(publication_id)

    mismatches = []
    for row in rows:
        person_id = row["person_id"]
        publications = author_publications[person_id]
        coauthors = set().union(*(publication_authors[value] for value in publications))
        coauthors.discard(person_id)
        if int(row["publication_count"]) != len(publications) or int(
            row["coauthor_count"]
        ) != len(coauthors):
            mismatches.append(row["person_id"])
    sort_keys = [
        (-int(row["publication_count"]), -int(row["coauthor_count"]), row["person_id"])
        for row in rows
    ]
    thresholds_hold = all(
        int(row["publication_count"]) >= int(parameters["min_publications"]) for row in rows
    )
    return {
        "passed": not mismatches and sort_keys == sorted(sort_keys) and thresholds_hold,
        "rows_checked": len(rows),
        "count_mismatches": mismatches,
        "ordering_valid": sort_keys == sorted(sort_keys),
        "thresholds_valid": thresholds_hold,
    }


def reference_distance(
    connection: psycopg.Connection[Any], parameters: dict[str, Any]
) -> int | None:
    edge_query = """
        SELECT DISTINCT a1.person_id AS left_id, a2.person_id AS right_id
        FROM publication
        JOIN authorship AS a1 USING (publication_id)
        JOIN authorship AS a2 ON a2.publication_id = publication.publication_id
                             AND a1.person_id < a2.person_id
        WHERE publication.year BETWEEN %(year_from)s AND %(year_to)s
          AND publication.venue_id = ANY(%(venue_ids)s)
    """
    edges = execute(connection, edge_query, parameters)
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in edges:
        adjacency[edge["left_id"]].add(edge["right_id"])
        adjacency[edge["right_id"]].add(edge["left_id"])
    source, target = parameters["source_id"], parameters["target_id"]
    queue = deque([(source, 0)])
    visited = {source}
    while queue:
        current, distance = queue.popleft()
        if current == target:
            return distance
        if distance == int(parameters["max_depth"]):
            continue
        for neighbour in adjacency[current] - visited:
            visited.add(neighbour)
            queue.append((neighbour, distance + 1))
    return None


def validate_q3(
    connection: psycopg.Connection[Any], rows: list[dict[str, Any]], parameters: dict[str, Any]
) -> dict[str, Any]:
    reference = reference_distance(connection, parameters)
    observed = int(rows[0]["distance"]) if rows else None
    return {
        "passed": observed == reference and len(rows) <= 1,
        "observed_distance": observed,
        "independent_bfs_distance": reference,
        "at_most_one_row": len(rows) <= 1,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@127.0.0.1:55432/dblp")
    parser.add_argument("--dataset", type=Path, default=Path("config/dataset.json"))
    parser.add_argument("--instances", type=Path, required=True)
    parser.add_argument("--query-dir", type=Path, default=Path("queries/sql"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    all_venues = [venue["id"] for venue in dataset["venues"]]
    instances = json.loads(args.instances.read_text(encoding="utf-8"))["instances"]
    enabled = [instance for instance in instances if instance.get("enabled", True)]
    validators = {"Q1": validate_q1, "Q2": validate_q2, "Q3": validate_q3}
    unsupported = sorted({instance["profile"] for instance in enabled} - set(validators))
    if unsupported:
        parser.error(f"PostgreSQL semantic validator accepts Q1-Q3 only: {', '.join(unsupported)}")

    checks = []
    with psycopg.connect(args.dsn) as connection:
        connection.execute(
            "SELECT set_config('statement_timeout', %s, false)",
            (f"{args.timeout_seconds}s",),
        )
        for instance in enabled:
            profile = instance["profile"]
            parameters = dict(instance["parameters"])
            if parameters.get("venue_ids") == "all":
                parameters["venue_ids"] = all_venues
            query = (args.query_dir / f"{profile.lower()}.sql").read_text(encoding="utf-8")
            rows = execute(connection, query, parameters)
            normalized, result_sha256 = normalize(rows)
            validation = validators[profile](connection, rows, parameters)
            checks.append(
                {
                    "query_family": profile,
                    "instance_id": instance["id"],
                    "parameters": instance["parameters"],
                    "row_count": len(normalized),
                    "result_sha256": result_sha256,
                    "validation": validation,
                }
            )
    payload = {
        "backend": "postgresql",
        "scope": ["Q1", "Q2", "Q3"],
        "passed": all(check["validation"]["passed"] for check in checks),
        "checks": checks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if not payload["passed"]:
        raise RuntimeError("one or more PostgreSQL semantic checks failed")


if __name__ == "__main__":
    main()
