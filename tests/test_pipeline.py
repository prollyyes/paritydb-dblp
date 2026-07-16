from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from rdflib import Graph

from dm_project.emit_rdf import emit
from dm_project.extract import extract


ROOT = Path(__file__).parents[1]


def test_extract_rejects_a_source_that_is_not_the_pinned_snapshot(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source MD5 mismatch"):
        extract(ROOT / "tests/fixtures/dblp_sample.nt", ROOT / "config/dataset.json", tmp_path)


def test_extract_is_deterministic_and_records_exclusions(tmp_path: Path) -> None:
    output = tmp_path / "canonical"
    metadata = extract(ROOT / "tests/fixtures/dblp_sample.nt", ROOT / "config/dataset.json", output, verify_source=False)

    assert metadata["counts"]["publications"] == 4
    assert metadata["counts"]["persons"] == 4
    assert metadata["counts"]["authorships"] == 6
    assert metadata["counts"]["excluded_multiple_selected_venues"] == 1
    assert metadata["counts"]["excluded_ambiguous_creators"] == 1

    with (output / "person.csv").open(encoding="utf-8", newline="") as source:
        people = list(csv.DictReader(source))
    assert [person["person_id"] for person in people] == sorted(person["person_id"] for person in people)
    assert sum(person["name"] == "Alex Kim" for person in people) == 2


def test_line_prefilters_never_skip_escaped_or_decoy_lines(tmp_path: Path) -> None:
    sample = tmp_path / "sample.nt"
    sample.write_text(
        "<https://dblp.org/rec/conf/kdd/P1> <https://dblp.org/rdf/schema#publishedInStream> <https://dblp.org/streams/conf/kdd> .\n"
        # The only title for P1 arrives on a line whose subject uses a UCHAR escape.
        '<https://dblp.org/rec/conf/kdd/P\\u0031> <https://dblp.org/rdf/schema#title> "Escaped subject" .\n'
        '<https://dblp.org/rec/conf/kdd/P1> <https://dblp.org/rdf/schema#yearOfPublication> "2010" .\n'
        "<https://dblp.org/rec/conf/kdd/P1> <https://dblp.org/rdf/schema#authoredBy> <https://dblp.org/pid/x> .\n"
        # A literal that merely mentions the routing predicate must stay inert.
        '<https://dblp.org/rec/conf/kdd/P2> <https://dblp.org/rdf/schema#title> "see <https://dblp.org/rdf/schema#publishedInStream>" .\n'
        '<https://dblp.org/pid/x> <https://dblp.org/rdf/schema#primaryCreatorName> "Xu Ali" .\n',
        encoding="utf-8",
    )
    config = tmp_path / "dataset.json"
    config.write_text(
        json.dumps(
            {
                "source": {},
                "year_from": 2005,
                "year_to": 2024,
                "max_publications": None,
                "venues": [
                    {"id": "https://dblp.org/streams/conf/kdd", "label": "KDD", "kind": "conference", "area": "data-mining"}
                ],
                "areas": [{"id": "data-mining", "label": "Data Mining", "parent": None}],
            }
        ),
        encoding="utf-8",
    )

    metadata = extract(sample, config, tmp_path / "out", verify_source=False)

    assert metadata["counts"]["publications"] == 1
    assert metadata["counts"]["persons"] == 1
    assert metadata["counts"]["authorships"] == 1
    with (tmp_path / "out" / "publication.csv").open(encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert rows == [
        {
            "publication_id": "https://dblp.org/rec/conf/kdd/P1",
            "title": "Escaped subject",
            "year": "2010",
            "venue_id": "https://dblp.org/streams/conf/kdd",
        }
    ]


def test_rdf_is_emitted_only_from_canonical_rows(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    extract(ROOT / "tests/fixtures/dblp_sample.nt", ROOT / "config/dataset.json", canonical, verify_source=False)
    output = tmp_path / "dataset.nt"
    count = emit(canonical, output)
    graph = Graph().parse(output, format="nt")

    assert count == len(graph)
    assert "https://dblp.org/rec/conf/multi/P4" not in {str(subject) for subject in graph.subjects()}
    assert "https://dblp.org/pid/e" not in {str(subject) for subject in graph.subjects()}
