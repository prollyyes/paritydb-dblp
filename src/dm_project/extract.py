"""Extract a deterministic canonical subset from a DBLP N-Triples snapshot."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Iterator

from rdflib import BNode, Literal, URIRef
from rdflib.plugins.parsers.ntriples import W3CNTriplesParser

DBLP = "https://dblp.org/rdf/schema#"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
PUBLISHED_IN_STREAM = URIRef(DBLP + "publishedInStream")
YEAR = URIRef(DBLP + "yearOfPublication")
TITLE = URIRef(DBLP + "title")
AUTHORED_BY = URIRef(DBLP + "authoredBy")
PRIMARY_NAME = URIRef(DBLP + "primaryCreatorName")
AMBIGUOUS_CREATOR = URIRef(DBLP + "AmbiguousCreator")


class _TripleSink:
    def __init__(self) -> None:
        self.triples: list[tuple[object, object, object]] = []

    def triple(self, subject: object, predicate: object, obj: object) -> None:
        self.triples.append((subject, predicate, obj))


def iter_triples(path: Path) -> Iterator[tuple[object, object, object]]:
    """Stream triples without assuming that subjects are adjacent in the dump."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as source:
        sink = _TripleSink()
        parser = W3CNTriplesParser(sink=sink)
        for line_number, line in enumerate(source, 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            sink.triples.clear()
            try:
                parser.parsestring(line)
            except Exception as exc:
                raise ValueError(f"invalid N-Triples at line {line_number}: {exc}") from exc
            yield from sink.triples


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def md5_file(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_csv(path: Path, columns: list[str], rows: Iterable[Iterable[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)


def extract(input_path: Path, config_path: Path, output_dir: Path, verify_source: bool = True) -> dict[str, object]:
    config_bytes = config_path.read_bytes()
    config = json.loads(config_bytes)
    source_md5 = md5_file(input_path)
    expected_md5 = config["source"].get("md5")
    if verify_source and expected_md5 and source_md5 != expected_md5:
        raise ValueError(f"source MD5 mismatch: expected {expected_md5}, got {source_md5}")
    venues = {venue["id"]: venue for venue in config["venues"]}
    year_from, year_to = int(config["year_from"]), int(config["year_to"])

    publication_venues: dict[str, set[str]] = defaultdict(set)
    for subject, predicate, obj in iter_triples(input_path):
        if predicate == PUBLISHED_IN_STREAM and str(obj) in venues:
            publication_venues[str(subject)].add(str(obj))

    # The canonical schema has one venue per publication. Cross-listed records are
    # excluded rather than assigned arbitrarily.
    candidates = {
        publication_id: next(iter(matched))
        for publication_id, matched in publication_venues.items()
        if len(matched) == 1
    }
    fields: dict[str, dict[str, object]] = defaultdict(dict)
    authors: dict[str, set[str]] = defaultdict(set)
    for subject, predicate, obj in iter_triples(input_path):
        publication_id = str(subject)
        if publication_id not in candidates:
            continue
        if predicate == YEAR and isinstance(obj, Literal):
            try:
                fields[publication_id]["year"] = int(str(obj))
            except ValueError:
                pass
        elif predicate == TITLE and isinstance(obj, Literal):
            fields[publication_id]["title"] = str(obj)
        elif predicate == AUTHORED_BY and isinstance(obj, URIRef):
            authors[publication_id].add(str(obj))

    eligible = [
        publication_id
        for publication_id in candidates
        if year_from <= int(fields[publication_id].get("year", -1)) <= year_to
        and fields[publication_id].get("title")
    ]
    limit = config.get("max_publications")
    if limit is not None:
        limit = int(limit)
        selected: set[str] = set()
        venue_order = sorted(venues)
        base, extra = divmod(limit, len(venue_order))
        for index, venue_id in enumerate(venue_order):
            quota = base + (index < extra)
            venue_candidates = [value for value in eligible if candidates[value] == venue_id]
            venue_candidates.sort(key=lambda value: hashlib.sha256(value.encode()).digest())
            selected.update(venue_candidates[:quota])
        if len(selected) < limit:
            remaining = [value for value in eligible if value not in selected]
            remaining.sort(key=lambda value: hashlib.sha256(value.encode()).digest())
            selected.update(remaining[: limit - len(selected)])
        eligible = sorted(selected)
    else:
        eligible.sort()
    eligible_set = set(eligible)
    creator_ids = {creator for publication_id in eligible for creator in authors[publication_id]}

    names: dict[str, str] = {}
    ambiguous: set[str] = set()
    for subject, predicate, obj in iter_triples(input_path):
        creator_id = str(subject)
        if creator_id not in creator_ids:
            continue
        if predicate == PRIMARY_NAME and isinstance(obj, Literal):
            names[creator_id] = str(obj)
        elif predicate == URIRef(RDF_TYPE) and obj == AMBIGUOUS_CREATOR:
            ambiguous.add(creator_id)
    creator_ids -= ambiguous

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        output_dir / "venue.csv",
        ["venue_id", "label", "venue_kind"],
        ((venue_id, venues[venue_id]["label"], venues[venue_id]["kind"]) for venue_id in sorted(venues)),
    )
    _write_csv(
        output_dir / "publication.csv",
        ["publication_id", "title", "year", "venue_id"],
        (
            (publication_id, fields[publication_id]["title"], fields[publication_id]["year"], candidates[publication_id])
            for publication_id in eligible
        ),
    )
    _write_csv(
        output_dir / "person.csv",
        ["person_id", "name"],
        ((creator_id, names.get(creator_id, creator_id.rsplit("/", 1)[-1])) for creator_id in sorted(creator_ids)),
    )
    _write_csv(
        output_dir / "authorship.csv",
        ["publication_id", "person_id", "author_position"],
        (
            (publication_id, creator_id, "")
            for publication_id in eligible
            for creator_id in sorted(authors[publication_id] & creator_ids)
        ),
    )
    _write_csv(
        output_dir / "area.csv",
        ["area_id", "label", "parent_area_id"],
        ((area["id"], area["label"], area["parent"] or "") for area in config["areas"]),
    )
    _write_csv(
        output_dir / "venue_area.csv",
        ["venue_id", "area_id"],
        ((venue_id, venues[venue_id]["area"]) for venue_id in sorted(venues)),
    )

    metadata: dict[str, object] = {
        "source": config["source"],
        "source_file": input_path.name,
        "source_md5": source_md5,
        "source_sha256": sha256_file(input_path),
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "venues": sorted(venues),
        "selection": {"year_from": year_from, "year_to": year_to, "max_publications": limit},
        "policy": {
            "multiple_selected_venues": "excluded",
            "ambiguous_creators": "excluded",
            "author_position": "not extracted; direct authoredBy has no ordering",
            "pilot_sampling": "stratified by venue, then stable SHA-256 of publication IRI"
        },
        "counts": {
            "publications": len(eligible_set),
            "persons": len(creator_ids),
            "authorships": sum(len(authors[publication_id] & creator_ids) for publication_id in eligible),
            "selected_venue_candidates": len(publication_venues),
            "excluded_multiple_selected_venues": sum(len(value) > 1 for value in publication_venues.values()),
            "excluded_ambiguous_creators": len(ambiguous),
            "missing_primary_names": sum(creator_id not in names for creator_id in creator_ids),
        },
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="DBLP .nt or .nt.gz snapshot")
    parser.add_argument("--config", type=Path, default=Path("config/dataset.json"))
    parser.add_argument("--output", type=Path, default=Path("data/canonical"))
    parser.add_argument("--allow-unverified-source", action="store_true", help="allow an input whose MD5 differs from the pinned release (fixtures only)")
    args = parser.parse_args()
    metadata = extract(args.input, args.config, args.output, verify_source=not args.allow_unverified_source)
    print(json.dumps(metadata["counts"], indent=2))


if __name__ == "__main__":
    main()
