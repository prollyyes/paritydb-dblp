from __future__ import annotations

import csv
from pathlib import Path

from dm_project.advisor import advise, recommend


ROOT = Path(__file__).parents[1]


def test_structural_rules_are_transparent() -> None:
    assert recommend({"needs_inference": True, "variable_path": False, "aggregation": True, "join_complexity": "hierarchy"})[0] == "fuseki"
    assert recommend({"needs_inference": False, "variable_path": True, "aggregation": False, "join_complexity": "recursive"})[0] == "fuseki"
    assert recommend({"needs_inference": False, "variable_path": False, "aggregation": True, "join_complexity": "shallow"})[0] == "postgresql"


def test_advisor_reports_evidence_winner_and_regret(tmp_path: Path) -> None:
    summary = tmp_path / "summary.csv"
    with summary.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=["query_family", "instance_id", "backend", "scale", "dataset_sha256", "correctness_passed", "median_ms", "min_ms", "max_ms", "runs"])
        writer.writeheader()
        writer.writerow({"query_family": "Q1", "instance_id": "case", "backend": "postgresql", "scale": "pilot", "dataset_sha256": "fixture", "correctness_passed": "true", "median_ms": 8, "min_ms": 7, "max_ms": 9, "runs": 5})
        writer.writerow({"query_family": "Q1", "instance_id": "case", "backend": "fuseki", "scale": "pilot", "dataset_sha256": "fixture", "correctness_passed": "true", "median_ms": 5, "min_ms": 4, "max_ms": 6, "runs": 5})
    result = advise("Q1", ROOT / "config/profiles.json", summary, "case", "pilot")
    assert result["recommendation"] == "postgresql"
    assert result["evidence"]["measured_winner"] == "fuseki"
    assert result["latency_regret_ms"] == 3
    assert result["warning"] is None


def test_advisor_does_not_invent_missing_evidence(tmp_path: Path) -> None:
    result = advise("Q3", ROOT / "config/profiles.json", tmp_path / "missing.csv", None, "pilot")
    assert result["evidence"] is None
    assert "No equivalent measured evidence" in result["warning"]
