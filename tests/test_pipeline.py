from __future__ import annotations

import csv
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


def test_rdf_is_emitted_only_from_canonical_rows(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    extract(ROOT / "tests/fixtures/dblp_sample.nt", ROOT / "config/dataset.json", canonical, verify_source=False)
    output = tmp_path / "dataset.nt"
    count = emit(canonical, output)
    graph = Graph().parse(output, format="nt")

    assert count == len(graph)
    assert "https://dblp.org/rec/conf/multi/P4" not in {str(subject) for subject in graph.subjects()}
    assert "https://dblp.org/pid/e" not in {str(subject) for subject in graph.subjects()}
