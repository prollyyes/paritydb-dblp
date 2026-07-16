from __future__ import annotations

import json

from dm_project.benchmark import (
    _progress,
    correctness_matches,
    execution_schedule,
)


def test_blocked_schedule_preserves_the_original_order() -> None:
    schedule = execution_schedule(2, 5, "blocked", 0)

    assert schedule[:7] == [
        ("warmup", 1, "postgresql"),
        ("warmup", 2, "postgresql"),
        ("measured", 1, "postgresql"),
        ("measured", 2, "postgresql"),
        ("measured", 3, "postgresql"),
        ("measured", 4, "postgresql"),
        ("measured", 5, "postgresql"),
    ]
    assert schedule[7:] == [
        ("warmup", 1, "fuseki"),
        ("warmup", 2, "fuseki"),
        ("measured", 1, "fuseki"),
        ("measured", 2, "fuseki"),
        ("measured", 3, "fuseki"),
        ("measured", 4, "fuseki"),
        ("measured", 5, "fuseki"),
    ]


def test_interleaved_schedule_alternates_without_changing_counts() -> None:
    schedule = execution_schedule(2, 5, "interleaved", 0)

    assert schedule[:4] == [
        ("warmup", 1, "fuseki"),
        ("warmup", 1, "postgresql"),
        ("warmup", 2, "postgresql"),
        ("warmup", 2, "fuseki"),
    ]
    assert schedule[4:8] == [
        ("measured", 1, "fuseki"),
        ("measured", 1, "postgresql"),
        ("measured", 2, "postgresql"),
        ("measured", 2, "fuseki"),
    ]
    for backend in ("postgresql", "fuseki"):
        assert sum(kind == "warmup" and name == backend for kind, _, name in schedule) == 2
        assert sum(kind == "measured" and name == backend for kind, _, name in schedule) == 5
    assert len(schedule) == 14
    assert 13 * (len(schedule) + 2) == 208


def test_interleaved_schedule_reverses_the_start_for_the_next_instance() -> None:
    first = execution_schedule(2, 5, "interleaved", 0)
    second = execution_schedule(2, 5, "interleaved", 1)

    assert first[0][2] == "fuseki"
    assert second[0][2] == "postgresql"


def test_correctness_gate_requires_equal_hash_and_row_count() -> None:
    checks = {
        "postgresql": {"row_count": 1, "result_sha256": "same"},
        "fuseki": {"row_count": 2, "result_sha256": "same"},
    }

    assert not correctness_matches(checks)
    checks["fuseki"]["row_count"] = 1
    assert correctness_matches(checks)


def test_progress_log_is_flushed_as_json_lines(tmp_path) -> None:
    path = tmp_path / "progress.jsonl"

    _progress(path, "instance_started", instance_id="q1", ordinal=1, total=13)
    record = json.loads(path.read_text(encoding="utf-8"))

    assert record["event"] == "instance_started"
    assert record["instance_id"] == "q1"
    assert record["ordinal"] == 1
    assert record["total"] == 13
    assert record["timestamp_utc"].endswith("+00:00")
