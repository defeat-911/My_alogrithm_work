"""Fill {{...}} placeholders in report_template.md from results/summary.json.

Placeholder forms:
    {{E2.500.alns.distance_km}}          mean, 2 decimals
    {{E2.500.alns.distance_km|1}}        mean, 1 decimal
    {{E2.500.alns.on_time_rate|pct}}     rate -> percent
    {{std:E2.500.alns.distance_km}}      standard deviation
    {{improve:E2.500.savings_2opt.distance_km:E2.500.alns.distance_km}}
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "docs" / "report" / "report_template.md"
OUTPUT = ROOT / "docs" / "report" / "report.md"
SUMMARY = ROOT / "results" / "summary.json"
OPTIMIZATION = ROOT / "results" / "optimization.json"

PATTERN = re.compile(r"\{\{([^{}]+)\}\}")


def _load_summary() -> dict:
    if not SUMMARY.exists():
        return {}
    with open(SUMMARY, "r", encoding="utf-8") as fh:
        return json.load(fh).get("summary", {})


def _load_optimization() -> dict:
    if not OPTIMIZATION.exists():
        return {}
    with open(OPTIMIZATION, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _resolve(summary: dict, path: str, stat: str = "mean") -> float | None:
    parts = path.split(".")
    if len(parts) < 4:
        return None
    exp, scale = parts[0], parts[1]
    metric = parts[-1]
    method = ".".join(parts[2:-1])
    try:
        return float(summary[exp][scale][method][metric][stat])
    except (KeyError, TypeError, ValueError):
        return None


def _fmt(value: float | None, spec: str = "") -> str:
    if value is None:
        return "—"
    if spec == "pct":
        return f"{value * 100:.1f}%"
    if spec == "int" or spec == "0":
        return f"{value:.0f}"
    if spec in {"1", "2", "3", "4"}:
        return f"{value:.{int(spec)}f}"
    return f"{value:.2f}" if isinstance(value, float) else str(value)


def _replace(summary: dict, optimization: dict, expr: str) -> str:
    expr = expr.strip()
    if expr.startswith("std:"):
        value = _resolve(summary, expr[4:], "std")
        return _fmt(value, "2")
    if expr.startswith("improve:"):
        _, p1, p2 = expr.split(":")
        v1 = _resolve(summary, p1)
        v2 = _resolve(summary, p2)
        if v1 in (None, 0) or v2 is None:
            return "—"
        return f"{(v1 - v2) / v1 * 100:.1f}%"
    if expr.startswith("OPT."):
        path, _, spec = expr.partition("|")
        value = optimization.get(path[4:])
        return _fmt(float(value) if value is not None else None, spec.strip())
    path, _, spec = expr.partition("|")
    value = _resolve(summary, path)
    return _fmt(value, spec.strip())


def main() -> None:
    summary = _load_summary()
    optimization = _load_optimization()
    text = TEMPLATE.read_text(encoding="utf-8")
    missing: list[str] = []

    def repl(match):
        expr = match.group(1)
        out = _replace(summary, optimization, expr)
        if out == "—":
            missing.append(expr)
        return out

    result = PATTERN.sub(repl, text)
    OUTPUT.write_text(result, encoding="utf-8")
    print(f"wrote {OUTPUT}")
    if missing:
        print(f"warning: {len(set(missing))} unique placeholders unresolved")
        for item in sorted(set(missing))[:30]:
            print("  missing:", item)


if __name__ == "__main__":
    sys.exit(main())
