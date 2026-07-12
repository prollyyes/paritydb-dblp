"""Emit the RDF representation from the canonical CSV files."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

DBLP = "https://dblp.org/rdf/schema#"
DM = "https://example.org/dm/schema#"
AREA = "https://example.org/dm/area/"


def _rows(directory: Path, filename: str) -> list[dict[str, str]]:
    with (directory / filename).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _triple(subject: URIRef, predicate: URIRef, obj: URIRef | Literal) -> str:
    return f"{subject.n3()} {predicate.n3()} {obj.n3()} .\n"


def emit(canonical_dir: Path, output_path: Path) -> int:
    triples: set[str] = set()
    for row in _rows(canonical_dir, "person.csv"):
        subject = URIRef(row["person_id"])
        triples.add(_triple(subject, RDF.type, URIRef(DBLP + "Person")))
        triples.add(_triple(subject, URIRef(DBLP + "primaryCreatorName"), Literal(row["name"])))
    for row in _rows(canonical_dir, "venue.csv"):
        subject = URIRef(row["venue_id"])
        kind = "Journal" if row["venue_kind"] == "journal" else "Conference"
        triples.add(_triple(subject, RDF.type, URIRef(DBLP + kind)))
        triples.add(_triple(subject, URIRef(DBLP + "primaryStreamTitle"), Literal(row["label"])))
    for row in _rows(canonical_dir, "publication.csv"):
        subject = URIRef(row["publication_id"])
        triples.add(_triple(subject, RDF.type, URIRef(DBLP + "Publication")))
        triples.add(_triple(subject, URIRef(DBLP + "title"), Literal(row["title"])))
        triples.add(_triple(subject, URIRef(DBLP + "yearOfPublication"), Literal(row["year"], datatype=XSD.gYear)))
        triples.add(_triple(subject, URIRef(DBLP + "publishedInStream"), URIRef(row["venue_id"])))
    for row in _rows(canonical_dir, "authorship.csv"):
        triples.add(_triple(URIRef(row["publication_id"]), URIRef(DBLP + "authoredBy"), URIRef(row["person_id"])))
    for row in _rows(canonical_dir, "area.csv"):
        subject = URIRef(AREA + row["area_id"])
        triples.add(_triple(subject, RDF.type, URIRef(DM + "ResearchArea")))
        triples.add(_triple(subject, RDFS.label, Literal(row["label"])))
        if row["parent_area_id"]:
            triples.add(_triple(subject, RDFS.subClassOf, URIRef(AREA + row["parent_area_id"])))
    for row in _rows(canonical_dir, "venue_area.csv"):
        triples.add(_triple(URIRef(row["venue_id"]), URIRef(DM + "assignedArea"), URIRef(AREA + row["area_id"])))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(sorted(triples)), encoding="utf-8")
    return len(triples)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, default=Path("data/canonical"))
    parser.add_argument("--output", type=Path, default=Path("data/rdf/dataset.nt"))
    args = parser.parse_args()
    print(f"wrote {emit(args.canonical, args.output)} triples to {args.output}")


if __name__ == "__main__":
    main()

