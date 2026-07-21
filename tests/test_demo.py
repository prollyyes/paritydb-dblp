from __future__ import annotations

import pytest

from dm_project.demo import compare_runs, select_instances


def _campaign() -> dict[str, object]:
    return {
        "scale": "full",
        "dataset_sha256": "dataset",
        "timeout_seconds": 300,
        "warmups": 2,
        "repetitions": 5,
        "execution_order": "interleaved",
        "success": True,
    }


def _instances() -> dict[str, object]:
    return {
        "instances": [
            {"id": "q1_a", "profile": "Q1", "enabled": True, "parameters": {"x": 1}},
            {"id": "q2_a", "profile": "Q2", "enabled": True, "parameters": {"x": 2}},
            {"id": "q1_b", "profile": "Q1", "enabled": True, "parameters": {"x": 3}},
        ]
    }


def _raw_rows() -> list[dict[str, str]]:
    rows = []
    for backend, times in (("postgresql", [10, 11, 12, 13, 14]), ("fuseki", [5, 6, 7, 8, 9])):
        for kind, count in (("first", 1), ("warmup", 2)):
            for number in range(1, count + 1):
                rows.append(
                    {
                        "query_family": "Q1",
                        "instance_id": "q1_a",
                        "backend": backend,
                        "run_kind": kind,
                        "run_number": str(number),
                        "elapsed_ms": "1.0",
                        "row_count": "3",
                        "result_sha256": "same",
                        "success": "True",
                        "error": "",
                    }
                )
        for number, elapsed in enumerate(times, 1):
            rows.append(
                {
                    "query_family": "Q1",
                    "instance_id": "q1_a",
                    "backend": backend,
                    "run_kind": "measured",
                    "run_number": str(number),
                    "elapsed_ms": str(elapsed),
                    "row_count": "3",
                    "result_sha256": "same",
                    "success": "True",
                    "error": "",
                }
            )
    return rows


def _accepted_summary() -> list[dict[str, str]]:
    return [
        {
            "query_family": "Q1",
            "instance_id": "q1_a",
            "backend": backend,
            "scale": "full",
            "dataset_sha256": "dataset",
            "correctness_passed": "true",
            "median_ms": median,
            "min_ms": median,
            "max_ms": median,
            "runs": "5",
        }
        for backend, median in (("postgresql", "8"), ("fuseki", "20"))
    ]


def test_selection_expands_families_deduplicates_and_preserves_order() -> None:
    selected = select_instances(_instances(), ["Q1", "q1_a"])

    assert [instance["id"] for instance in selected["instances"]] == ["q1_a", "q1_b"]


def test_selection_rejects_unknown_names() -> None:
    with pytest.raises(ValueError, match="unknown family or instance"):
        select_instances(_instances(), ["Q9"])


def test_comparison_validates_protocol_and_reports_a_flip() -> None:
    accepted_instances = _instances()
    live_instances = {"instances": [accepted_instances["instances"][0]]}

    rows, metadata = compare_runs(
        _raw_rows(),
        _campaign(),
        live_instances,
        _accepted_summary(),
        _campaign(),
        accepted_instances,
    )

    assert rows[0]["live_postgresql_median_ms"] == 12
    assert rows[0]["live_fuseki_median_ms"] == 7
    assert rows[0]["live_winner"] == "fuseki"
    assert rows[0]["accepted_winner"] == "postgresql"
    assert rows[0]["winner_flip"] is True
    assert metadata["winner_flips"] == 1
    assert metadata["authoritative_campaign_replaced"] is False


def test_comparison_refuses_a_different_runtime_protocol() -> None:
    live_campaign = _campaign()
    live_campaign["warmups"] = 1
    accepted_instances = _instances()

    with pytest.raises(ValueError, match="live protocol differs"):
        compare_runs(
            _raw_rows(),
            live_campaign,
            {"instances": [accepted_instances["instances"][0]]},
            _accepted_summary(),
            _campaign(),
            accepted_instances,
        )


def test_comparison_refuses_changed_results_after_the_first_gate() -> None:
    raw_rows = _raw_rows()
    raw_rows[-1]["result_sha256"] = "changed"
    accepted_instances = _instances()

    with pytest.raises(ValueError, match="result signatures changed"):
        compare_runs(
            raw_rows,
            _campaign(),
            {"instances": [accepted_instances["instances"][0]]},
            _accepted_summary(),
            _campaign(),
            accepted_instances,
        )
