"""Deterministically select representative PostgreSQL Q3 pilot pairs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dsn", default="postgresql://postgres:postgres@127.0.0.1:55432/dblp")
    parser.add_argument("--dataset", type=Path, default=Path("config/dataset.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    venue_ids = [venue["id"] for venue in dataset["venues"]]
    parameters = (dataset["year_from"], dataset["year_to"], venue_ids)
    with psycopg.connect(args.dsn) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT person_id, name FROM person ORDER BY person_id")
            names = {row["person_id"]: row["name"] for row in cursor}
            cursor.execute(
                """
                SELECT DISTINCT a1.person_id AS left_id, a2.person_id AS right_id
                FROM publication AS publication
                JOIN authorship AS a1 USING (publication_id)
                JOIN authorship AS a2 ON a2.publication_id = publication.publication_id
                                     AND a1.person_id < a2.person_id
                WHERE publication.year BETWEEN %s AND %s
                  AND publication.venue_id = ANY(%s)
                ORDER BY left_id, right_id
                """,
                parameters,
            )
            edges = [(row["left_id"], row["right_id"]) for row in cursor]

    adjacency: dict[str, set[str]] = defaultdict(set)
    for left_id, right_id in edges:
        adjacency[left_id].add(right_id)
        adjacency[right_id].add(left_id)

    moderate_edges = [
        edge
        for edge in edges
        if 3 <= len(adjacency[edge[0]]) <= 12 and 3 <= len(adjacency[edge[1]]) <= 12
    ]
    if not moderate_edges:
        raise RuntimeError("no moderate-degree direct pair found")
    direct = min(
        moderate_edges,
        key=lambda edge: (len(adjacency[edge[0]]) + len(adjacency[edge[1]]), edge),
    )

    distance_three: tuple[str, str, list[str]] | None = None
    sources = sorted(node for node, neighbours in adjacency.items() if 2 <= len(neighbours) <= 8)
    for source in sources:
        queue = deque([source])
        distance = {source: 0}
        parent: dict[str, str] = {}
        while queue:
            current = queue.popleft()
            if distance[current] == 3:
                continue
            for neighbour in sorted(adjacency[current]):
                if neighbour in distance:
                    continue
                distance[neighbour] = distance[current] + 1
                parent[neighbour] = current
                queue.append(neighbour)
        targets = sorted(
            node for node, value in distance.items() if value == 3 and 2 <= len(adjacency[node]) <= 8
        )
        if not targets:
            continue
        target = targets[0]
        path = [target]
        while path[-1] != source:
            path.append(parent[path[-1]])
        distance_three = (source, target, list(reversed(path)))
        break
    if distance_three is None:
        raise RuntimeError("no moderate-degree distance-3 pair found")

    def describe(person_id: str) -> dict[str, Any]:
        return {
            "person_id": person_id,
            "name": names[person_id],
            "eligible_coauthor_degree": len(adjacency[person_id]),
        }

    source, target, path = distance_three
    payload = {
        "backend": "postgresql",
        "eligible_graph": {
            "year_from": dataset["year_from"],
            "year_to": dataset["year_to"],
            "venue_ids": venue_ids,
            "people_with_edges": len(adjacency),
            "undirected_edges": len(edges),
        },
        "direct": {
            "source": describe(direct[0]),
            "target": describe(direct[1]),
            "expected_distance": 1,
        },
        "distance_three": {
            "source": describe(source),
            "target": describe(target),
            "expected_distance": 3,
            "witness_path": [describe(person_id) for person_id in path],
        },
        "out_of_bound": {
            "source_id": source,
            "target_id": target,
            "max_depth": 2,
            "expected_result": "no row",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
