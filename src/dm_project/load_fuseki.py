"""Replace the Fuseki dataset with the canonical N-Triples representation."""

from __future__ import annotations

import argparse
import base64
import urllib.request
from pathlib import Path


def load(graph_store_url: str, rdf_path: Path, username: str | None, password: str | None) -> None:
    request = urllib.request.Request(
        graph_store_url + "?default",
        data=rdf_path.read_bytes(),
        method="PUT",
        headers={"Content-Type": "application/n-triples"},
    )
    if username:
        token = base64.b64encode(f"{username}:{password or ''}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=300) as response:
        if response.status not in (200, 201, 204):
            raise RuntimeError(f"Fuseki returned HTTP {response.status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rdf", type=Path, nargs="?", default=Path("data/rdf/dataset.nt"))
    parser.add_argument("--graph-store-url", default="http://localhost:3030/dblp/data")
    parser.add_argument("--username")
    parser.add_argument("--password")
    args = parser.parse_args()
    load(args.graph_store_url, args.rdf, args.username, args.password)
    print("Fuseki load complete")


if __name__ == "__main__":
    main()

