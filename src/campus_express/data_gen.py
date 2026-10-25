"""Reproducible package generation and task aggregation."""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Any, Iterable

from .models import (
    Campus,
    Package,
    Priority,
    Task,
    TimeWindow,
    format_hhmm,
    parse_hhmm,
)

KIND_WEIGHTS = {
    "dorm": 0.60,
    "teaching": 0.25,
    "library": 0.03,
    "canteen": 0.05,
    "gym": 0.02,
    "admin": 0.01,
    "lab": 0.02,
    "hospital": 0.01,
    "innovation": 0.01,
}


class InfeasibleInstance(ValueError):
    """Raised when the generated instance cannot satisfy capacity limits."""


def bucket_windows(config: dict[str, Any]) -> dict[int, TimeWindow]:
    result: dict[int, TimeWindow] = {}
    for item in config["packages"]["buckets"]:
        result[int(item["id"])] = TimeWindow(
            parse_hhmm(item["start"]), parse_hhmm(item["end"])
        )
    return result


def _destination_weights(campus: Campus) -> tuple[list[str], list[float]]:
    ids: list[str] = []
    weights: list[float] = []
    for pid in campus.point_ids:
        kind = campus.points[pid].kind
        ids.append(pid)
        weights.append(KIND_WEIGHTS.get(kind, 0.01))
    total = sum(weights)
    return ids, [w / total for w in weights]


def _make_window(
    bucket: TimeWindow, priority: Priority, rng: random.Random
) -> TimeWindow:
    if priority == Priority.EXPRESS:
        end = min(bucket.start_min + 60, bucket.end_min)
    elif priority == Priority.URGENT:
        end = min(bucket.start_min + 90, bucket.end_min)
    else:
        end = bucket.end_min
    return TimeWindow(bucket.start_min, end)


def _make_weight(config: dict[str, Any], rng: random.Random) -> float:
    low = float(config["packages"]["weight_min_kg"])
    high = float(config["packages"]["weight_max_kg"])
    light_max = float(config["packages"].get("light_max_kg", 0.8))
    heavy_fraction = float(config["packages"].get("heavy_fraction", 0.10))
    if rng.random() < heavy_fraction:
        return rng.uniform(light_max, high)
    return rng.uniform(low, light_max)


def check_instance(
    packages: list[Package],
    campus: Campus,
    config: dict[str, Any],
) -> dict[str, Any]:
    courier_cfg = config["couriers"]
    chute_capacity = sum(c.capacity_packages for c in campus.chutes.values())
    courier_capacity = (
        int(courier_cfg["count"]) * int(courier_cfg["capacity_packages"])
    )
    courier_weight = (
        int(courier_cfg["count"]) * float(courier_cfg["capacity_kg"])
    )
    total_weight = sum(p.weight_kg for p in packages)
    per_point: dict[str, int] = defaultdict(int)
    for pkg in packages:
        per_point[pkg.dest_id] += 1
    max_point = max(per_point.values()) if per_point else 0
    max_chute = max((c.capacity_packages for c in campus.chutes.values()), default=0)
    reasons: list[str] = []
    if not packages:
        reasons.append("empty package list")
    if len(packages) > 0.95 * chute_capacity:
        reasons.append(
            f"packages {len(packages)} > 95% chute capacity {chute_capacity}"
        )
    if len(packages) > 0.95 * courier_capacity:
        reasons.append(
            f"packages {len(packages)} > 95% courier capacity {courier_capacity}"
        )
    if total_weight > 0.95 * courier_weight:
        reasons.append(
            f"weight {total_weight:.1f} kg > 95% courier weight {courier_weight:.1f} kg"
        )
    if max_point > max_chute:
        reasons.append(f"single point demand {max_point} > chute capacity {max_chute}")
    return {
        "n": len(packages),
        "total_weight_kg": round(total_weight, 3),
        "chute_capacity": chute_capacity,
        "courier_capacity_packages": courier_capacity,
        "courier_capacity_kg": courier_weight,
        "max_point_demand": max_point,
        "feasible": not reasons,
        "reasons": reasons,
    }


def generate_packages(
    campus: Campus,
    n: int,
    seed: int,
    config: dict[str, Any],
) -> list[Package]:
    if n <= 0:
        raise ValueError("n must be positive")
    rng = random.Random(seed)
    bucket_map = bucket_windows(config)
    bucket_ids = sorted(bucket_map)
    ids, weights = _destination_weights(campus)
    priority_values = [1, 2, 3]
    priority_weights = [
        float(config["packages"]["priority_probs"][1]),
        float(config["packages"]["priority_probs"][2]),
        float(config["packages"]["priority_probs"][3]),
    ]
    cap_per_point = max(c.capacity_packages for c in campus.chutes.values())
    demand: dict[str, int] = defaultdict(int)
    packages: list[Package] = []

    def add_one(point_id: str) -> None:
        priority = Priority(
            rng.choices(priority_values, weights=priority_weights, k=1)[0]
        )
        bucket_id = rng.choice(bucket_ids)
        window = _make_window(bucket_map[bucket_id], priority, rng)
        packages.append(
            Package(
                id=f"PKG{len(packages) + 1:06d}",
                dest_id=point_id,
                weight_kg=round(_make_weight(config, rng), 3),
                priority=priority,
                window=window,
                bucket=bucket_id,
            )
        )
        demand[point_id] += 1

    # Guarantee coverage when there are at least as many packages as points.
    # For tiny instances (n < 30) sample distinct points instead.
    if n < len(ids):
        for pid in rng.sample(ids, n):
            add_one(pid)
    else:
        for pid in ids:
            add_one(pid)
        while len(packages) < n:
            pid = rng.choices(ids, weights=weights, k=1)[0]
            if demand[pid] >= cap_per_point:
                candidates = [p for p in ids if demand[p] < cap_per_point]
                if not candidates:
                    raise InfeasibleInstance(
                        f"cannot place {n} packages with per-point cap {cap_per_point}"
                    )
                pid = min(candidates, key=lambda p: (demand[p], p))
            add_one(pid)

    report = check_instance(packages, campus, config)
    if not report["feasible"]:
        raise InfeasibleInstance(
            "generated instance is infeasible: " + "; ".join(report["reasons"])
        )
    return packages


def aggregate_tasks(
    packages: Iterable[Package],
    campus: Campus,
    config: dict[str, Any],
) -> list[Task]:
    """Aggregate packages into ``(point, bucket)`` tasks.

    The task window is the bucket window; urgency is preserved by
    ``priority_score`` (package-count-weighted priority) and by the routing
    objective's priority-weighted arrival term.  This keeps the task count at
    roughly 60--120 for 500 packages while avoiding a plain ``max`` that would
    erase the express signal.
    """

    stop_s = float(config["couriers"]["service_s_per_stop"])
    per_pkg_s = float(config["couriers"]["service_s_per_package"])
    bucket_map = bucket_windows(config)
    groups: dict[tuple[str, int], list[Package]] = defaultdict(list)
    for pkg in packages:
        groups[(pkg.dest_id, pkg.bucket)].append(pkg)

    tasks: list[Task] = []
    for (point_id, bucket_id), items in sorted(groups.items()):
        # Use the intersection of the package windows in the group.  This
        # preserves urgency: a group containing an express package gets the
        # express sub-window instead of the full bucket window.
        start = max(p.window.start_min for p in items)
        end = min(p.window.end_min for p in items)
        window = (
            TimeWindow(start, end)
            if start < end
            else bucket_map[bucket_id]
        )
        demand = len(items)
        weight_kg = sum(p.weight_kg for p in items)
        priority = max(p.priority for p in items)
        priority_score = sum(int(p.priority) for p in items) / demand
        tasks.append(
            Task(
                id=f"T_{point_id}_{bucket_id}",
                point_id=point_id,
                window=window,
                package_ids=tuple(p.id for p in items),
                demand=demand,
                weight_kg=weight_kg,
                priority=priority,
                priority_score=priority_score,
                service_s=stop_s + per_pkg_s * demand,
            )
        )
    if not tasks:
        raise ValueError("no tasks produced")
    seen = [pid for task in tasks for pid in task.package_ids]
    if len(seen) != len(set(seen)):
        raise AssertionError("package assigned to more than one task")
    return tasks


def save_dataset(
    campus: Campus,
    packages: list[Package],
    n: int,
    seed: int,
    config: dict[str, Any],
    path: str,
) -> None:
    from .io import save_packages

    save_packages(
        packages,
        path,
        meta={
            "n": n,
            "seed": seed,
            "generator": "campus_express 0.1.0",
            "campus": campus.name,
            "buckets": [
                {
                    "id": int(b["id"]),
                    "start": b["start"],
                    "end": b["end"],
                }
                for b in config["packages"]["buckets"]
            ],
        },
    )
