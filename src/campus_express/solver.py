"""End-to-end sorting + routing pipeline."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .data_gen import aggregate_tasks
from .graph import RoadNetwork
from .io import load_campus, load_config, load_packages
from .models import Campus, Courier, Package, Solution, Task, parse_hhmm
from .routing.alns import ALNSParams, ALNSResult, alns
from .routing.baselines import cheapest_insertion, nn_edd
from .routing.common import RoutingContext
from .routing.local_search import polish_routes
from .routing.savings import clarke_wright
from .sorting.baselines import sort_grid, sort_sweep
from .sorting.common import Assignment, evaluate_assignment
from .sorting.kmeans import capacitated_kmeans, kmeanspp
from .sorting.local_search import sort_capacitated


@dataclass
class PipelineContext:
    campus: Campus
    config: dict[str, Any]
    packages: list[Package]
    tasks: list[Task]
    network: RoadNetwork
    dist: np.ndarray
    point_index: dict[str, int]
    routing: RoutingContext


@dataclass
class PipelineResult:
    campus: str
    n_packages: int
    n_tasks: int
    sorting_method: str
    routing_method: str
    sorting: Assignment
    solution: Solution
    runtime_s: float
    alns: ALNSResult | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        routes = []
        for route in self.solution.routes:
            schedule = self.extra.get("schedules", {}).get(route.courier_id)
            routes.append(
                {
                    "courier_id": route.courier_id,
                    "task_ids": route.task_ids,
                    "point_ids": [
                        self.extra.get("task_points", {}).get(tid, "")
                        for tid in route.task_ids
                    ],
                    "load": schedule.load if schedule else 0,
                    "distance_m": schedule.distance_m if schedule else 0.0,
                    "end_time": schedule.end_time if schedule else 0.0,
                }
            )
        return {
            "campus": self.campus,
            "n_packages": self.n_packages,
            "n_tasks": self.n_tasks,
            "sorting_method": self.sorting_method,
            "routing_method": self.routing_method,
            "runtime_s": round(self.runtime_s, 3),
            "sorting": {
                "labels": dict(sorted(self.sorting.labels.items())),
                "loads": self.sorting.loads,
                "metrics": self.sorting.metrics,
            },
            "routes": routes,
            "metrics": self.solution.metrics,
            "alns": (
                {
                    "iterations": self.alns.iterations,
                    "runtime_s": round(self.alns.runtime_s, 3),
                    "convergence": self.alns.convergence,
                }
                if self.alns
                else None
            ),
        }

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)


def build_context_from_data(
    campus: Campus,
    config: dict[str, Any],
    packages: list[Package],
    couriers_count: int | None = None,
    hard_windows: bool | None = None,
) -> PipelineContext:
    tasks = aggregate_tasks(packages, campus, config)
    network = RoadNetwork(campus)
    ids = campus.key_node_ids
    dist = network.distance_matrix(ids)
    point_index = {pid: i + 1 for i, pid in enumerate(campus.point_ids)}
    count = int(couriers_count or config["couriers"]["count"])
    couriers = [
        Courier(
            id=i,
            capacity_packages=int(config["couriers"]["capacity_packages"]),
            capacity_kg=float(config["couriers"]["capacity_kg"]),
            speed_mps=float(config["couriers"]["speed_mps"]),
            shift_start=parse_hhmm(config["couriers"]["shift_start"]),
            shift_end=parse_hhmm(config["couriers"]["shift_end"]),
        )
        for i in range(count)
    ]
    routing = RoutingContext(
        tasks={t.id: t for t in tasks},
        task_order=[t.id for t in tasks],
        point_index=point_index,
        dist=dist,
        couriers=couriers,
        shift_start=couriers[0].shift_start,
        shift_end=couriers[0].shift_end,
        hard_windows=(
            bool(config["routing"].get("hard_windows", True))
            if hard_windows is None
            else hard_windows
        ),
        weights=config["objective"]["weights"],
    )
    return PipelineContext(
        campus=campus,
        config=config,
        packages=packages,
        tasks=tasks,
        network=network,
        dist=dist,
        point_index=point_index,
        routing=routing,
    )


def build_context(
    campus_path: str | Path = "data/campus.json",
    packages_path: str | Path = "data/packages_300.json",
    config_path: str | Path = "config/default.yaml",
    couriers_count: int | None = None,
    hard_windows: bool | None = None,
) -> PipelineContext:
    campus = load_campus(campus_path)
    config = load_config(config_path)
    packages = load_packages(packages_path)
    return build_context_from_data(
        campus,
        config,
        packages,
        couriers_count=couriers_count,
        hard_windows=hard_windows,
    )


def _sorting_inputs(ctx: PipelineContext):
    demand = ctx.campus.demand_by_point(ctx.packages)
    ids = ctx.campus.point_ids
    points_xy = {
        pid: (ctx.campus.points[pid].x_m, ctx.campus.points[pid].y_m)
        for pid in ids
    }
    capacity = min(c.capacity_packages for c in ctx.campus.chutes.values())
    return demand, ids, points_xy, capacity


def solve_sorting(
    ctx: PipelineContext, method: str = "cap_ls", seed: int = 1
) -> Assignment:
    demand, ids, points_xy, capacity = _sorting_inputs(ctx)
    k = len(ctx.campus.chutes)
    if method == "grid":
        assignment = sort_grid(ids, demand, k, points_xy)
    elif method == "sweep":
        assignment = sort_sweep(
            ids,
            demand,
            k,
            (ctx.campus.center.x_m, ctx.campus.center.y_m),
            points_xy,
        )
    elif method == "kmeans":
        assignment = kmeanspp(
            ids,
            points_xy,
            demand,
            k,
            seed=seed,
            n_init=int(ctx.config["sorting"]["kmeans_restarts"]),
            max_iter=int(ctx.config["sorting"]["max_iter"]),
        )
    elif method == "cap_kmeans":
        assignment = capacitated_kmeans(
            ids,
            points_xy,
            demand,
            k,
            capacity,
            seed=seed,
            n_init=int(ctx.config["sorting"]["kmeans_restarts"]),
            max_iter=int(ctx.config["sorting"]["max_iter"]),
        )
    elif method == "cap_ls":
        assignment = sort_capacitated(
            ids,
            points_xy,
            demand,
            k,
            capacity,
            ctx.campus,
            ctx.dist,
            ctx.point_index,
            seed=seed,
            n_init=int(ctx.config["sorting"]["kmeans_restarts"]),
            max_iter=int(ctx.config["sorting"]["max_iter"]),
            cv_penalty=float(ctx.config["sorting"]["cv_penalty"]),
            local_search_time_s=float(
                ctx.config["sorting"].get("local_search_time_s", 5.0)
            ),
        )
    else:
        raise ValueError(f"unknown sorting method: {method}")
    return evaluate_assignment(
        assignment,
        ctx.campus,
        ctx.dist,
        ctx.point_index,
        demand,
        capacity,
        cv_penalty=float(ctx.config["sorting"]["cv_penalty"]),
    )


def solve_routing(
    ctx: PipelineContext,
    method: str = "alns",
    seed: int = 1,
    quick: bool = False,
    time_limit_s: float | None = None,
) -> tuple[Solution, ALNSResult | None]:
    routing_ctx = ctx.routing
    if method == "nn":
        return nn_edd(routing_ctx), None
    if method == "insertion":
        return cheapest_insertion(routing_ctx), None
    if method == "savings":
        return clarke_wright(routing_ctx), None
    if method == "savings_2opt":
        return polish_routes(routing_ctx, clarke_wright(routing_ctx)), None
    if method != "alns":
        raise ValueError(f"unknown routing method: {method}")

    s1 = polish_routes(routing_ctx, clarke_wright(routing_ctx))
    s2 = cheapest_insertion(routing_ctx)
    initial = s1 if s1.metrics["objective"] <= s2.metrics["objective"] else s2
    cfg = ctx.config["routing"]
    limit = float(cfg["time_limit_s"]) if time_limit_s is None else float(time_limit_s)
    params = ALNSParams(
        iterations=int(cfg["alns_quick_iterations"] if quick else cfg["alns_iterations"]),
        destroy_fraction=float(cfg["destroy_fraction"]),
        t0_ratio=float(cfg["t0_ratio"]),
        tend_ratio=float(cfg["tend_ratio"]),
        segment=int(cfg["segment"]),
        reaction=float(cfg["reaction"]),
        seed=seed,
        time_limit_s=limit,
    )
    result = alns(routing_ctx, initial, params)
    return result.best, result


def solve(
    packages_path: str | Path,
    campus_path: str | Path = "data/campus.json",
    config_path: str | Path = "config/default.yaml",
    sorting_method: str = "cap_ls",
    routing_method: str = "alns",
    couriers_count: int | None = None,
    seed: int = 1,
    quick: bool = False,
    hard_windows: bool | None = None,
) -> PipelineResult:
    start = time.perf_counter()
    ctx = build_context(
        campus_path=campus_path,
        packages_path=packages_path,
        config_path=config_path,
        couriers_count=couriers_count,
        hard_windows=hard_windows,
    )
    sorting = solve_sorting(ctx, sorting_method, seed=seed)
    solution, alns_result = solve_routing(
        ctx, routing_method, seed=seed, quick=quick
    )
    schedules = {}
    for route in solution.routes:
        schedules[route.courier_id] = ctx.routing.schedule_route(
            route.courier_id, route.task_ids
        )
    extra = {
        "schedules": schedules,
        "task_points": {t.id: t.point_id for t in ctx.tasks},
    }
    return PipelineResult(
        campus=ctx.campus.name,
        n_packages=len(ctx.packages),
        n_tasks=len(ctx.tasks),
        sorting_method=sorting_method,
        routing_method=routing_method,
        sorting=sorting,
        solution=solution,
        runtime_s=time.perf_counter() - start,
        alns=alns_result,
        extra=extra,
    )
