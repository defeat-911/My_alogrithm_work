"""Merge the quick 100/300 summary with the 500-only backup summary.

The full 5-seed run can take a long time on a throttled laptop.  This script
lets the report use the completed quick 100/300 results plus a 3-seed 500-only
run, while keeping all numbers traceable to results/*.json.
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results" / "summary.json"
EXTRA = ROOT / "results" / "summary_500.json"
OUT_JSON = ROOT / "results" / "summary_merged.json"
OUT_CSV = ROOT / "results" / "metrics_merged.csv"


def main() -> None:
    if not EXTRA.exists():
        raise SystemExit(f"missing {EXTRA}")
    with open(BASE, "r", encoding="utf-8") as fh:
        base = json.load(fh)
    with open(EXTRA, "r", encoding="utf-8") as fh:
        extra = json.load(fh)

    rows: dict[tuple, dict] = {}
    for row in base.get("rows", []):
        key = (
            row["experiment"],
            str(row["scale"]),
            row["seed"],
            row["method"],
            row["metric"],
        )
        rows[key] = row
    for row in extra.get("rows", []):
        key = (
            row["experiment"],
            str(row["scale"]),
            row["seed"],
            row["method"],
            row["metric"],
        )
        rows[key] = row
    merged_rows = sorted(
        rows.values(),
        key=lambda r: (r["experiment"], str(r["scale"]), r["seed"], r["method"], r["metric"]),
    )

    merged_summary = copy.deepcopy(base.get("summary", {}))
    for exp, scales in extra.get("summary", {}).items():
        for scale, methods in scales.items():
            merged_summary.setdefault(exp, {})[scale] = methods

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(
            {"rows": merged_rows, "summary": merged_summary},
            fh,
            ensure_ascii=False,
            indent=2,
        )
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["experiment", "scale", "seed", "method", "metric", "value"]
        )
        writer.writeheader()
        writer.writerows(merged_rows)
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_CSV}")
    print("scales:", {e: sorted(v) for e, v in merged_summary.items()})


if __name__ == "__main__":
    main()
