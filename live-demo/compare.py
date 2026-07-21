#!/usr/bin/env python3
"""Compare a live benchmark run against the accepted campaign medians.

Usage:
    python live-demo/compare.py LIVE_CSV [ACCEPTED_SUMMARY_CSV]

LIVE_CSV is a raw dm-benchmark output (demo.sh run passes its own).
The accepted summary defaults to results/final/summary.csv.
Prints per-instance medians for both environments, the winner on each side,
and flags every instance where the measured winner differs.
"""

import csv
import statistics
import sys
from pathlib import Path

if len(sys.argv) < 2:
    sys.exit(__doc__.strip())
live_path = Path(sys.argv[1])
accepted_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("results/final/summary.csv")

live_runs: dict[tuple[str, str], list[float]] = {}
with live_path.open() as fh:
    for row in csv.DictReader(fh):
        if row["run_kind"] != "measured" or row["success"] != "True":
            continue
        live_runs.setdefault((row["instance_id"], row["backend"]), []).append(float(row["elapsed_ms"]))

accepted: dict[tuple[str, str], float] = {}
order: list[str] = []
with accepted_path.open() as fh:
    for row in csv.DictReader(fh):
        accepted[(row["instance_id"], row["backend"])] = float(row["median_ms"])
        if row["instance_id"] not in order:
            order.append(row["instance_id"])

def winner(pg: float, fu: float) -> str:
    return "postgresql" if pg < fu else "fuseki"

header = (
    f"{'instance':<28} {'live PG':>10} {'live FU':>10} {'live win':>10} "
    f"{'camp PG':>10} {'camp FU':>10} {'camp win':>10}  flip"
)
print(header)
print("-" * len(header))

flips = 0
compared = 0
for inst in order:
    lp = live_runs.get((inst, "postgresql"))
    lf = live_runs.get((inst, "fuseki"))
    if not (lp and lf):
        continue  # instance not part of this live run
    cp = accepted.get((inst, "postgresql"))
    cf = accepted.get((inst, "fuseki"))
    if cp is None or cf is None:
        print(f"{inst:<28} (no accepted campaign medians)")
        continue
    compared += 1
    lpm, lfm = statistics.median(lp), statistics.median(lf)
    lw, cw = winner(lpm, lfm), winner(cp, cf)
    flip = "  <-- WINNER FLIP" if lw != cw else ""
    if flip:
        flips += 1
    print(
        f"{inst:<28} {lpm:>10.1f} {lfm:>10.1f} {lw:>10} "
        f"{cp:>10.1f} {cf:>10.1f} {cw:>10}{flip}"
    )

print(f"\n{compared} instance(s) compared, {flips} winner flip(s) relative to the accepted campaign.")
