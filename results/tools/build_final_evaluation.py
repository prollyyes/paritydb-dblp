"""Build auditable advisor tables and figures from one accepted campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from dm_project.advisor import recommend


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def write_advisor(
    path: Path,
    summary: list[dict[str, str]],
    instances: list[dict[str, Any]],
    profiles: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    medians = {
        (row["query_family"], row["instance_id"], row["backend"]): float(row["median_ms"])
        for row in summary
    }
    rows: list[dict[str, Any]] = []
    for instance in instances:
        profile = instance["profile"]
        recommendation, reason = recommend(profiles[profile])
        postgres = medians[(profile, instance["id"], "postgresql")]
        fuseki = medians[(profile, instance["id"], "fuseki")]
        winner = "postgresql" if postgres < fuseki else "fuseki"
        regret = {"postgresql": postgres, "fuseki": fuseki}[recommendation] - min(
            postgres, fuseki
        )
        rows.append(
            {
                "profile": profile,
                "instance_id": instance["id"],
                "recommendation": recommendation,
                "reason": reason,
                "postgresql_median_ms": f"{postgres:.3f}",
                "fuseki_median_ms": f"{fuseki:.3f}",
                "measured_winner": winner,
                "match": recommendation == winner,
                "latency_regret_ms": f"{regret:.3f}",
                "warning": "",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_replication(
    path: Path,
    current: list[dict[str, str]],
    archived: list[dict[str, str]],
) -> None:
    old = {
        (row["query_family"], row["instance_id"], row["backend"]): float(row["median_ms"])
        for row in archived
    }
    rows = []
    for row in current:
        key = (row["query_family"], row["instance_id"], row["backend"])
        archived_median = old[key]
        controlled_median = float(row["median_ms"])
        rows.append(
            {
                "query_family": key[0],
                "instance_id": key[1],
                "backend": key[2],
                "archived_median_ms": f"{archived_median:.3f}",
                "controlled_median_ms": f"{controlled_median:.3f}",
                "controlled_to_archived_ratio": f"{controlled_median / archived_median:.3f}",
            }
        )
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_audit(
    path: Path,
    benchmark: list[dict[str, str]],
    summary: list[dict[str, str]],
) -> list[dict[str, Any]]:
    counts = Counter(
        (row["instance_id"], row["backend"], row["run_kind"]) for row in benchmark
    )
    expected = {"first": 1, "warmup": 2, "measured": 5}
    count_failures = [
        {"instance_id": key[0], "backend": key[1], "run_kind": key[2], "count": value}
        for key, value in sorted(counts.items())
        if value != expected[key[2]]
    ]
    first: dict[tuple[str, str], dict[str, dict[str, str]]] = defaultdict(dict)
    measured: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for row in benchmark:
        if row["run_kind"] == "first":
            first[(row["query_family"], row["instance_id"])][row["backend"]] = row
        if row["run_kind"] == "measured" and row["success"] == "True":
            measured[(row["query_family"], row["instance_id"], row["backend"])].append(
                float(row["elapsed_ms"])
            )
    correctness_failures = []
    for (profile, instance_id), pair in sorted(first.items()):
        if (
            pair["postgresql"]["row_count"] != pair["fuseki"]["row_count"]
            or pair["postgresql"]["result_sha256"]
            != pair["fuseki"]["result_sha256"]
        ):
            correctness_failures.append({"profile": profile, "instance_id": instance_id})
    variability = []
    for (profile, instance_id, backend), values in sorted(measured.items()):
        median = statistics.median(values)
        spread = (max(values) - min(values)) / median
        variability.append(
            {
                "query_family": profile,
                "instance_id": instance_id,
                "backend": backend,
                "median_ms": round(median, 3),
                "min_ms": round(min(values), 3),
                "max_ms": round(max(values), 3),
                "spread_ratio": round(spread, 4),
                "flagged_over_10_percent": spread > 0.10,
            }
        )
    summary_failures = []
    for row in summary:
        key = (row["query_family"], row["instance_id"], row["backend"])
        values = measured[key]
        expected_values = {
            "median_ms": f"{statistics.median(values):.3f}",
            "min_ms": f"{min(values):.3f}",
            "max_ms": f"{max(values):.3f}",
            "runs": str(len(values)),
        }
        if any(row[field] != value for field, value in expected_values.items()):
            summary_failures.append(
                {"query_family": key[0], "instance_id": key[1], "backend": key[2]}
            )
    all_successful = all(row["success"] == "True" for row in benchmark)
    audit = {
        "raw_rows": len(benchmark),
        "expected_raw_rows": 208,
        "summary_rows": len(summary),
        "expected_summary_rows": 26,
        "all_executions_successful": all_successful,
        "execution_count_failures": count_failures,
        "paired_correctness_failures": correctness_failures,
        "summary_recomputation_failures": summary_failures,
        "observed_execution_groups": len(counts),
        "expected_execution_groups": 78,
        "observed_first_pairs": len(first),
        "expected_first_pairs": 13,
        "observed_measured_series": len(measured),
        "expected_measured_series": 26,
        "variability_threshold": 0.10,
        "flagged_series": sum(row["flagged_over_10_percent"] for row in variability),
        "total_series": len(variability),
        "accepted": (
            not count_failures
            and not correctness_failures
            and not summary_failures
            and all_successful
            and len(benchmark) == 208
            and len(summary) == 26
            and len(counts) == 78
            and len(first) == 13
            and len(measured) == 26
        ),
        "variability_interpretation": (
            "No external disturbance, timeout, service failure, or configuration change was "
            "identified. Preserve all runs and report median plus min/max; do not cherry-pick."
        ),
        "series": variability,
    }
    path.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return variability


def write_evidence_hashes(directory: Path) -> None:
    output = directory / "evidence-sha256.json"
    hashes = {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file() and path != output
    }
    output.write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")


def build_figures(
    directory: Path,
    summary: list[dict[str, str]],
    benchmark: list[dict[str, str]],
    advisor: list[dict[str, Any]],
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    labels = [row["instance_id"] for row in advisor]
    postgres = [float(row["postgresql_median_ms"]) for row in advisor]
    fuseki = [float(row["fuseki_median_ms"]) for row in advisor]
    positions = list(range(len(labels)))

    fig, axis = plt.subplots(figsize=(10, 7))
    axis.barh([value + 0.2 for value in positions], postgres, height=0.38, label="PostgreSQL")
    axis.barh([value - 0.2 for value in positions], fuseki, height=0.38, label="Fuseki")
    axis.set_xscale("log")
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlabel("Median measured latency (ms, log scale)")
    axis.legend()
    axis.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(directory / "fig1_median_by_instance.png", dpi=180)
    plt.close(fig)

    first = {
        (row["query_family"], row["instance_id"], row["backend"]): float(row["elapsed_ms"])
        for row in benchmark
        if row["run_kind"] == "first"
    }
    medians = {
        (row["query_family"], row["instance_id"], row["backend"]): float(row["median_ms"])
        for row in summary
    }
    fig, axis = plt.subplots(figsize=(7, 7))
    for backend, marker in (("postgresql", "o"), ("fuseki", "s")):
        keys = [key for key in medians if key[2] == backend]
        axis.scatter(
            [medians[key] for key in keys],
            [first[key] for key in keys],
            label=backend.capitalize(),
            marker=marker,
            alpha=0.8,
        )
    limits = [
        min(min(medians.values()), min(first.values())),
        max(max(medians.values()), max(first.values())),
    ]
    axis.plot(limits, limits, color="gray", linewidth=1)
    axis.set_xscale("log")
    axis.set_yscale("log")
    axis.set_xlabel("Measured median (ms, log scale)")
    axis.set_ylabel("First observed execution (ms, log scale)")
    axis.legend()
    axis.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(directory / "fig2_first_vs_measured.png", dpi=180)
    plt.close(fig)

    regrets = [float(row["latency_regret_ms"]) for row in advisor]
    fig, axis = plt.subplots(figsize=(10, 7))
    axis.barh(positions, regrets)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xlabel("Advisor latency regret (ms)")
    axis.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(directory / "fig3_advisor_regret.png", dpi=180)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-dir", type=Path, default=Path("results/final"))
    parser.add_argument("--profiles", type=Path, default=Path("config/profiles.json"))
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("results/archive/20260712-235644-full"),
    )
    args = parser.parse_args()
    summary = read_csv(args.final_dir / "summary.csv")
    benchmark = read_csv(args.final_dir / "benchmark.csv")
    instances = json.loads((args.final_dir / "instances.json").read_text(encoding="utf-8"))[
        "instances"
    ]
    profiles = json.loads(args.profiles.read_text(encoding="utf-8"))
    advisor = write_advisor(
        args.final_dir / "advisor_evaluation.csv", summary, instances, profiles
    )
    write_replication(
        args.final_dir / "replication_comparison.csv",
        summary,
        read_csv(args.archive_dir / "summary.csv"),
    )
    write_audit(args.final_dir / "audit.json", benchmark, summary)
    build_figures(args.final_dir / "figures", summary, benchmark, advisor)
    write_evidence_hashes(args.final_dir)


if __name__ == "__main__":
    main()
