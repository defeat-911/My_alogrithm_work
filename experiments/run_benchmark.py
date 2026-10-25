"""Run the v1 experiment matrix and write results/metrics.csv + summary.json.

Usage:
    python experiments/run_benchmark.py --scales 100 300 500 --seeds 1 2 3
    python experiments/run_benchmark.py --quick
"""

from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from campus_express.data_gen import (
    InfeasibleInstance,
    aggregate_tasks,
    check_instance,
    generate_packages,
)
from campus_express.io import load_campus, load_config
from campus_express.models import Courier, Package, Priority, Task, TimeWindow
from campus_express.routing.alns import ALNSParams, alns
from campus_express.routing.common import RoutingContext
from campus_express.routing.exact import (
    branch_and_bound_tw,
    brute_force_tsp,
    brute_force_tw,
    held_karp,
)
from campus_express.routing.local_search import polish_routes
from campus_express.routing.savings import clarke_wright
from campus_express.solver import (
    build_context_from_data,
    solve_routing,
    solve_sorting,
)
from campus_express.utils import nearest_neighbor_tour, two_opt_tour, tour_length

RESULTS = ROOT / "results"

METRIC_KEYS = [
    "feasible",
    "n_packages",
    "n_tasks",
    "distance_km",
    "makespan_min",
    "on_time_rate",
    "tardiness_min",
    "priority_weighted_arrival",
    "load_cv",
    "unassigned",
    "objective",
    "runtime_s",
    "alns_iterations",
    "tsp_proxy_m",
    "max_load_ratio",
    "overflow_packages",
    "empty_clusters",
    "silhouette",
    "optimal_cost",
    "heuristic_cost",
    "gap_pct",
    "bruteforce_cost",
    "bnb_cost",
    "match",
]


def _mean_std(values: list[float]) -> tuple[float, float]:
    clean = [v for v in values if v is not None and math.isfinite(v)]
    if not clean:
        return (float("nan"), float("nan"))
    return (statistics.mean(clean), statistics.pstdev(clean) if len(clean) > 1 else 0.0)


def make_config_with_buckets(
    config: dict[str, Any], buckets: list[tuple[str, str]]
) -> dict[str, Any]:
    cfg = copy.deepcopy(config)
    cfg["packages"]["buckets"] = [
        {"id": i, "start": start, "end": end}
        for i, (start, end) in enumerate(buckets)
    ]
    return cfg


def make_ctx(
    campus,
    config: dict[str, Any],
    n: int,
    seed: int,
    couriers: int | None = None,
    hard_windows: bool = True,
):
    packages = generate_packages(campus, n, seed, config)
    return build_context_from_data(
        campus,
        config,
        packages,
        couriers_count=couriers,
        hard_windows=hard_windows,
    )


def record(
    rows: list[dict[str, Any]],
    experiment: str,
    scale: int | str,
    seed: int,
    method: str,
    metrics: dict[str, Any],
) -> None:
    for key in METRIC_KEYS:
        if key in metrics and metrics[key] is not None:
            value = metrics[key]
            if isinstance(value, (int, float)) and math.isfinite(float(value)):
                rows.append(
                    {
                        "experiment": experiment,
                        "scale": scale,
                        "seed": seed,
                        "method": method,
                        "metric": key,
                        "value": float(value),
                    }
                )


def run_e1(campus, config, scales, seeds, rows):
    print("[E1] sorting")
    for n in scales:
        for seed in seeds:
            ctx = make_ctx(campus, config, n, seed)
            for method in ["grid", "sweep", "kmeans", "cap_kmeans", "cap_ls"]:
                start = time.perf_counter()
                assignment = solve_sorting(ctx, method=method, seed=seed)
                runtime = time.perf_counter() - start
                metrics = dict(assignment.metrics)
                metrics["runtime_s"] = runtime
                metrics["n_packages"] = len(ctx.packages)
                record(rows, "E1", n, seed, method, metrics)


def run_e2(campus, config, scales, seeds, rows, alns_time_s, convergence_dir: Path):
    print("[E2] routing")
    for n in scales:
        for seed in seeds:
            ctx = make_ctx(campus, config, n, seed)
            for method in ["nn", "insertion", "savings", "savings_2opt"]:
                start = time.perf_counter()
                solution, _ = solve_routing(ctx, method=method, seed=seed)
                runtime = time.perf_counter() - start
                metrics = dict(solution.metrics)
                metrics["runtime_s"] = runtime
                metrics["n_packages"] = len(ctx.packages)
                metrics["n_tasks"] = len(ctx.tasks)
                record(rows, "E2", n, seed, method, metrics)
            # ALNS from the better of savings+2opt and insertion.
            s1 = polish_routes(ctx.routing, clarke_wright(ctx.routing))
            s2, _ = solve_routing(ctx, method="insertion", seed=seed)
            initial = s1 if s1.metrics["objective"] <= s2.metrics["objective"] else s2
            result = alns(
                ctx.routing,
                initial,
                ALNSParams(iterations=1500, seed=seed, time_limit_s=alns_time_s),
            )
            metrics = dict(result.best.metrics)
            metrics["runtime_s"] = result.runtime_s
            metrics["alns_iterations"] = result.iterations
            metrics["n_packages"] = len(ctx.packages)
            metrics["n_tasks"] = len(ctx.tasks)
            record(rows, "E2", n, seed, "alns", metrics)
            convergence_dir.mkdir(parents=True, exist_ok=True)
            with open(convergence_dir / f"convergence_{n}_{seed}.json", "w", encoding="utf-8") as fh:
                json.dump(result.convergence, fh)


def run_e4(campus, config, seeds, rows):
    print("[E4] courier count")
    for couriers in [2, 4, 6, 8]:
        for seed in seeds[:3]:
            ctx = make_ctx(campus, config, 300, seed, couriers=couriers)
            solution, _ = solve_routing(ctx, method="savings_2opt", seed=seed)
            metrics = dict(solution.metrics)
            metrics["n_packages"] = len(ctx.packages)
            metrics["n_tasks"] = len(ctx.tasks)
            record(rows, "E4", 300, seed, f"couriers_{couriers}", metrics)


def run_e5(campus, config, seeds, rows, alns_time_s):
    print("[E5] time-window width sensitivity")
    variants = {
        "tight_20min": [("08:00", "08:20"), ("09:00", "09:20"), ("10:00", "10:20"), ("11:00", "11:20")],
        "medium_30min": [("08:00", "08:30"), ("10:00", "10:30"), ("14:00", "14:30"), ("16:00", "16:30")],
        "default_2h": [("08:00", "10:00"), ("10:00", "12:00"), ("14:00", "16:00"), ("16:00", "18:00")],
        "wide_3_4h": [("08:00", "11:00"), ("11:00", "14:00"), ("14:00", "18:00")],
    }
    for name, buckets in variants.items():
        cfg = make_config_with_buckets(config, buckets)
        for seed in seeds[:3]:
            ctx = make_ctx(campus, cfg, 300, seed)
            initial = polish_routes(ctx.routing, clarke_wright(ctx.routing))
            result = alns(
                ctx.routing,
                initial,
                ALNSParams(iterations=800, seed=seed, time_limit_s=alns_time_s),
            )
            metrics = dict(result.best.metrics)
            metrics["runtime_s"] = result.runtime_s
            metrics["n_packages"] = len(ctx.packages)
            metrics["n_tasks"] = len(ctx.tasks)
            record(rows, "E5", 300, seed, name, metrics)


def run_e6(campus, config, seeds, rows, alns_time_s):
    print("[E6] ablation: priority weight")
    for weight in [0.0, 0.2, 0.4]:
        cfg = copy.deepcopy(config)
        cfg["objective"]["weights"]["priority"] = weight
        for seed in seeds[:2]:
            ctx = make_ctx(campus, cfg, 500, seed)
            initial = polish_routes(ctx.routing, clarke_wright(ctx.routing))
            result = alns(
                ctx.routing,
                initial,
                ALNSParams(iterations=800, seed=seed, time_limit_s=alns_time_s),
            )
            metrics = dict(result.best.metrics)
            metrics["runtime_s"] = result.runtime_s
            metrics["n_packages"] = len(ctx.packages)
            metrics["n_tasks"] = len(ctx.tasks)
            record(rows, "E6", 500, seed, f"priority_{weight:.1f}", metrics)


def run_e7(rows):
    print("[E7] exact validation")
    for n in [6, 7, 8, 9, 10]:
        for seed in range(1, 6):
            rng = np.random.default_rng(seed)
            points = rng.uniform(0, 100, size=(n, 2))
            diff = points[:, None, :] - points[None, :, :]
            dist = np.sqrt((diff**2).sum(axis=2))
            start = time.perf_counter()
            optimal, _ = held_karp(dist)
            exact_time = time.perf_counter() - start
            tour = nearest_neighbor_tour(list(range(n)), dist, start=0)
            tour = two_opt_tour(tour, dist)
            heuristic = tour_length(tour, dist)
            gap = (heuristic - optimal) / optimal * 100 if optimal else 0.0
            record(
                rows,
                "E7",
                n,
                seed,
                "nk_2opt_vs_held_karp",
                {
                    "optimal_cost": optimal,
                    "heuristic_cost": heuristic,
                    "gap_pct": gap,
                    "runtime_s": exact_time,
                },
            )
    # Time-window branch-and-bound vs brute force on small synthetic routes.
    for n in [5, 6, 7]:
        ctx = _synthetic_tw_context(n)
        bf = brute_force_tw(ctx, ctx.task_order, 0)
        bb = branch_and_bound_tw(ctx, ctx.task_order, 0, time_limit_s=10.0)
        record(
            rows,
            "E7",
            n,
            1,
            "bnb_vs_bruteforce_tw",
            {
                "bruteforce_cost": bf.cost,
                "bnb_cost": bb.cost,
                "match": 1.0 if math.isclose(bf.cost, bb.cost, rel_tol=1e-9, abs_tol=1e-9) else 0.0,
                "runtime_s": bb.runtime_s,
            },
        )


def _synthetic_tw_context(n: int) -> RoutingContext:
    rng = np.random.default_rng(42 + n)
    points = rng.uniform(0, 100, size=(n + 1, 2))
    diff = points[:, None, :] - points[None, :, :]
    dist = np.sqrt((diff**2).sum(axis=2))
    tasks = {}
    for i in range(1, n + 1):
        tid = f"T{i}"
        tasks[tid] = Task(
            id=tid,
            point_id=f"P{i}",
            window=TimeWindow(480, 700),
            package_ids=(f"p{i}",),
            demand=1,
            weight_kg=0.5,
            priority=Priority.NORMAL,
            priority_score=1.0,
            service_s=60.0,
        )
    return RoutingContext(
        tasks=tasks,
        task_order=list(tasks),
        point_index={f"P{i}": i for i in range(1, n + 1)},
        dist=dist,
        couriers=[Courier(0, 20, 20.0, 1.0, 480, 1080)],
        shift_start=480,
        shift_end=1080,
        hard_windows=True,
    )


def run_e8(campus, config, rows):
    print("[E8] edge cases")
    scenarios: list[tuple[str, Any]] = []

    # 1 package
    try:
        pkgs = generate_packages(campus, 1, 1, config)
        scenarios.append(("single_package", check_instance(pkgs, campus, config)))
    except Exception as exc:
        scenarios.append(("single_package", {"feasible": 0.0, "error": str(exc)}))

    # 0 packages
    scenarios.append(("zero_packages", check_instance([], campus, config)))

    # over-capacity single point
    fake = [
        Package(
            id=f"P{i}",
            dest_id="D01",
            weight_kg=0.5,
            priority=Priority.NORMAL,
            window=TimeWindow(480, 600),
            bucket=0,
        )
        for i in range(61)
    ]
    scenarios.append(("single_point_over_capacity", check_instance(fake, campus, config)))

    # 1 courier on 100 packages
    ctx = make_ctx(campus, config, 100, 1, couriers=1)
    solution, _ = solve_routing(ctx, method="savings_2opt", seed=1)
    scenarios.append(
        (
            "one_courier_100",
            {
                "feasible": solution.metrics["feasible"],
                "unassigned": solution.metrics["unassigned"],
                "n_tasks": solution.metrics["n_tasks"],
            },
        )
    )
    for name, metrics in scenarios:
        record(rows, "E8", 0, 1, name, metrics)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[tuple[str, str, str, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[
            (
                row["experiment"],
                str(row["scale"]),
                row["method"],
                row["metric"],
            )
        ].append(row["value"])
    summary: dict[str, Any] = {}
    for (experiment, scale, method, metric), values in sorted(grouped.items()):
        mean, std = _mean_std(values)
        summary.setdefault(experiment, {}).setdefault(scale, {}).setdefault(
            method, {}
        )[metric] = {
            "mean": mean,
            "std": std,
            "n": len(values),
        }
    return summary


def write_outputs(rows: list[dict[str, Any]], out_csv: Path, out_json: Path) -> None:
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["experiment", "scale", "seed", "method", "metric", "value"]
        )
        writer.writeheader()
        writer.writerows(rows)
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "rows": rows,
                "summary": summarize(rows),
            },
            fh,
            ensure_ascii=False,
            indent=2,
        )
    print(f"wrote {out_csv}")
    print(f"wrote {out_json}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scales", type=int, nargs="+", default=[100, 300, 500])
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    parser.add_argument("--alns-time", type=float, default=20.0)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", default=str(RESULTS / "metrics.csv"))
    parser.add_argument("--json", default=str(RESULTS / "summary.json"))
    args = parser.parse_args()

    scales = [100, 300] if args.quick else args.scales
    seeds = [1] if args.quick else args.seeds
    alns_time = 5.0 if args.quick else args.alns_time

    campus = load_campus(ROOT / "data" / "campus.json")
    config = load_config(ROOT / "config" / "default.yaml")
    rows: list[dict[str, Any]] = []
    convergence_dir = RESULTS / "convergence"
    run_e1(campus, config, scales, seeds, rows)
    run_e2(campus, config, scales, seeds, rows, alns_time, convergence_dir)
    run_e4(campus, config, seeds, rows)
    run_e5(campus, config, seeds, rows, alns_time)
    run_e6(campus, config, seeds, rows, alns_time)
    run_e7(rows)
    run_e8(campus, config, rows)
    write_outputs(rows, Path(args.out), Path(args.json))


if __name__ == "__main__":
    main()
