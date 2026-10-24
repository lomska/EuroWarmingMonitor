"""Record how long each dbt model took in the last dbt run.

Reads dbt/target/run_results.json, prints the slowest models, and appends
every model's time to perf/timings.csv under a label, so runs can be compared.

Usage (from the project folder, right after a dbt build):
    python perf/timings.py --label europe-before
    python perf/timings.py --compare europe-before europe-after
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path

RUN_RESULTS = Path("dbt/target/run_results.json")
CSV_FILE = Path("perf/timings.csv")
FIELDS = ["label", "recorded_at", "model", "status", "seconds", "rows"]


def record(label: str) -> None:
    results = json.loads(RUN_RESULTS.read_text(encoding="utf-8"))
    rows = []
    for r in results["results"]:
        if not r["unique_id"].startswith("model."):
            continue
        rows.append(
            {
                "label": label,
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
                "model": r["unique_id"].split(".")[-1],
                "status": r["status"],
                "seconds": round(r["execution_time"], 2),
                "rows": (r.get("adapter_response") or {}).get("rows_affected", ""),
            }
        )
    if not rows:
        raise SystemExit("No model results in run_results.json; run dbt build first.")

    new_file = not CSV_FILE.exists()
    with CSV_FILE.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if new_file:
            writer.writeheader()
        writer.writerows(rows)

    rows.sort(key=lambda r: r["seconds"], reverse=True)
    total = sum(r["seconds"] for r in rows)
    print(
        f"{label}: {len(rows)} models, {total:.1f} s of model time "
        f"(whole command: {results['elapsed_time']:.1f} s)"
    )
    for r in rows[:10]:
        print(f"  {r['seconds']:>8.2f} s  {r['model']}  ({r['rows']} rows)")
    print(f"Saved to {CSV_FILE}")


def compare(before: str, after: str) -> None:
    with CSV_FILE.open(encoding="utf-8") as f:
        data = list(csv.DictReader(f))
    # the latest recording of each label wins
    times = {before: {}, after: {}}
    for row in data:
        if row["label"] in times:
            times[row["label"]][row["model"]] = float(row["seconds"])
    if not times[before] or not times[after]:
        raise SystemExit(f"Need recordings for both {before!r} and {after!r} in {CSV_FILE}.")

    models = sorted(times[before], key=lambda m: times[before][m], reverse=True)
    print(f"{'model':36} {before:>14} {after:>14}   change")
    for m in models:
        b, a = times[before][m], times[after].get(m)
        if a is None:
            continue
        change = f"{(a - b) / b:+.0%}" if b > 0 else ""
        print(f"{m:36} {b:>12.2f} s {a:>12.2f} s   {change}")
    tb, ta = sum(times[before].values()), sum(times[after].values())
    print(f"{'TOTAL':36} {tb:>12.2f} s {ta:>12.2f} s   {(ta - tb) / tb:+.0%}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--label", help="name for this run, e.g. europe-before")
    group.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    if args.label:
        record(args.label)
    else:
        compare(*args.compare)


if __name__ == "__main__":
    main()
