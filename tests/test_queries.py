from __future__ import annotations

import json
from pathlib import Path

from rdflib import Graph
from rdflib.plugins.sparql.parser import parseQuery

from dm_project.benchmark import build_path_branches, normalize, render_sparql
from dm_project.emit_rdf import emit
from dm_project.extract import extract


ROOT = Path(__file__).parents[1]
DATASET = json.loads((ROOT / "config/dataset.json").read_text(encoding="utf-8"))
BASE = {"year_from": 2005, "year_to": 2024, "venue_ids": "all"}


def test_all_sparql_templates_parse_after_rendering() -> None:
    parameters = {
        "Q1": {**BASE, "bucket": "decade"},
        "Q2": {**BASE, "min_publications": 1, "limit": 10},
        "Q3": {**BASE, "source_id": "https://dblp.org/pid/a", "target_id": "https://dblp.org/pid/d", "max_depth": 4},
        "Q4": {**BASE, "source_id": "https://dblp.org/pid/a", "min_mutuals": 1, "limit": 10},
        "Q5": {**BASE, "ancestor_area": "computer-science", "min_distinct_areas": 2},
    }
    for profile, values in parameters.items():
        template = (ROOT / "queries/sparql" / f"{profile.lower()}.rq").read_text(encoding="utf-8")
        parseQuery(render_sparql(template, values, DATASET))


def test_all_sparql_queries_execute_with_expected_fixture_results(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    extract(ROOT / "tests/fixtures/dblp_sample.nt", ROOT / "config/dataset.json", canonical, verify_source=False)
    rdf_path = tmp_path / "dataset.nt"
    emit(canonical, rdf_path)
    graph = Graph().parse(rdf_path, format="nt")
    parameters = {
        "Q1": {**BASE, "bucket": "decade"},
        "Q2": {**BASE, "min_publications": 1, "limit": 10},
        "Q3": {**BASE, "source_id": "https://dblp.org/pid/a", "target_id": "https://dblp.org/pid/d", "max_depth": 4},
        "Q4": {**BASE, "source_id": "https://dblp.org/pid/a", "min_mutuals": 1, "limit": 10},
        "Q5": {**BASE, "ancestor_area": "computer-science", "min_distinct_areas": 2},
    }
    results = {}
    for profile, values in parameters.items():
        template = (ROOT / "queries/sparql" / f"{profile.lower()}.rq").read_text(encoding="utf-8")
        results[profile] = [tuple(str(value) for value in row) for row in graph.query(render_sparql(template, values, DATASET))]

    assert len(results["Q1"]) == 2
    assert results["Q3"] == [("https://dblp.org/pid/a", "https://dblp.org/pid/d", "3")]
    assert results["Q4"] == [("https://dblp.org/pid/c", "Casey Li", "1")]
    assert results["Q5"] == [("https://dblp.org/pid/b", "Blair Rao", "2", "2")]


def test_path_generation_has_every_bounded_depth_and_zero_identity() -> None:
    parameters = {**BASE, "source_id": "https://dblp.org/pid/a", "target_id": "https://dblp.org/pid/d", "max_depth": 3}
    branches = build_path_branches(parameters, "<https://dblp.org/streams/conf/kdd>")
    assert "BIND(1 AS ?candidate_distance)" in branches
    assert "BIND(2 AS ?candidate_distance)" in branches
    assert "BIND(3 AS ?candidate_distance)" in branches
    assert branches.count("UNION") == 2

    parameters["target_id"] = parameters["source_id"]
    assert build_path_branches(parameters, "") == "BIND(0 AS ?candidate_distance)"


def test_normalization_ignores_backend_types_and_row_order() -> None:
    left = [{"person_id": "b", "publication_count": 2}, {"person_id": "a", "publication_count": 1}]
    right = [{"publication_count": "1", "person_id": "a"}, {"publication_count": "2", "person_id": "b"}]
    assert normalize(left)[1] == normalize(right)[1]
