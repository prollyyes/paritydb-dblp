"""Explainable routing advisor for the five frozen query profiles."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


def recommend(profile: dict[str, Any]) -> tuple[str, str]:
    if profile["needs_inference"]:
        return "fuseki", "the query follows a declared research-area hierarchy"
    if profile["variable_path"]:
        return "fuseki", "the query contains bounded or variable-length graph traversal"
    if profile["aggregation"] and profile["join_complexity"] in {"shallow", "self_join"}:
        return "postgresql", "SQL expresses the grouped tabular aggregation directly"
    return "run_both", "the structural profile has no decisive rule"


def evidence(
    summary_path: Path,
    profile_id: str,
    instance_id: str,
    scale: str,
    dataset_digest: str | None,
) -> dict[str, Any] | None:
    if not summary_path.exists():
        return None
    with summary_path.open(encoding="utf-8", newline="") as source:
        rows = [
            row for row in csv.DictReader(source)
            if row["instance_id"] == instance_id
            and row["query_family"] == profile_id
            and row.get("scale") == scale
            and row.get("correctness_passed") == "true"
            and int(row.get("runs", 0)) >= 5
            and (dataset_digest is None or row.get("dataset_sha256") == dataset_digest)
        ]
    if {row["backend"] for row in rows} != {"postgresql", "fuseki"}:
        return None
    medians = {row["backend"]: float(row["median_ms"]) for row in rows}
    winner = min(medians, key=medians.get)
    return {"medians_ms": medians, "measured_winner": winner}


def advise(
    profile_id: str,
    profiles_path: Path,
    summary_path: Path,
    instance_id: str | None,
    scale: str,
    dataset_path: Path | None = None,
) -> dict[str, Any]:
    profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    if profile_id not in profiles:
        raise ValueError(f"unknown profile {profile_id}; choose one of {', '.join(profiles)}")
    backend, reason = recommend(profiles[profile_id])
    result: dict[str, Any] = {
        "profile": profile_id,
        "scale": scale,
        "recommendation": backend,
        "reason": reason,
        "evidence_instance": instance_id,
        "evidence": None,
        "warning": "No equivalent measured evidence was supplied; this is a structural recommendation."
    }
    dataset_digest = hashlib.sha256(dataset_path.read_bytes()).hexdigest() if dataset_path else None
    measured = evidence(summary_path, profile_id, instance_id, scale, dataset_digest) if instance_id else None
    if measured:
        result["evidence"] = measured
        result["warning"] = None
        if backend in measured["medians_ms"]:
            result["latency_regret_ms"] = round(
                measured["medians_ms"][backend] - min(measured["medians_ms"].values()), 3
            )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=["Q1", "Q2", "Q3", "Q4", "Q5"])
    parser.add_argument("--scale", default="pilot")
    parser.add_argument("--instance")
    parser.add_argument("--profiles", type=Path, default=Path("config/profiles.json"))
    parser.add_argument("--summary", type=Path, default=Path("results/summary.csv"))
    parser.add_argument("--dataset", type=Path, default=Path("config/dataset.json"))
    args = parser.parse_args()
    print(json.dumps(advise(args.profile, args.profiles, args.summary, args.instance, args.scale, args.dataset), indent=2))


if __name__ == "__main__":
    main()
