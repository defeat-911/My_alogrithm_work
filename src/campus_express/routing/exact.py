"""Small-instance exact solvers used for correctness checks."""

from __future__ import annotations

import itertools
import math
import time
from dataclasses import dataclass

import numpy as np

from .common import RoutingContext


@dataclass
class ExactResult:
    cost: float
    task_ids: list[str]
    proven: bool
    runtime_s: float
    method: str


def held_karp(dist: np.ndarray) -> tuple[float, list[int]]:
    """Exact TSP over a complete symmetric matrix (depot index 0).

    Complexity O(n^2 2^n); intended for n <= 12.
    """

    n = int(dist.shape[0])
    if n <= 1:
        return 0.0, [0]
    if n > 15:
        raise ValueError("Held-Karp is limited to n <= 15")
    size = 1 << (n - 1)
    dp = np.full((size, n - 1), np.inf, dtype=float)
    parent = np.full((size, n - 1), -1, dtype=int)
    for j in range(n - 1):
        dp[1 << j, j] = float(dist[0, j + 1])
    for mask in range(size):
        for j in range(n - 1):
            if not (mask & (1 << j)) or not math.isfinite(dp[mask, j]):
                continue
            for k in range(n - 1):
                if mask & (1 << k):
                    continue
                new_mask = mask | (1 << k)
                cand = dp[mask, j] + float(dist[j + 1, k + 1])
                if cand < dp[new_mask, k] - 1e-12:
                    dp[new_mask, k] = cand
                    parent[new_mask, k] = j
    full = size - 1
    best_cost = math.inf
    best_last = -1
    for j in range(n - 1):
        cand = dp[full, j] + float(dist[j + 1, 0])
        if cand < best_cost:
            best_cost = cand
            best_last = j
    tour = [0]
    mask = full
    last = best_last
    order = []
    while last != -1:
        order.append(last + 1)
        prev = parent[mask, last]
        mask ^= 1 << last
        last = prev
    order.reverse()
    tour.extend(order)
    tour.append(0)
    return float(best_cost), tour


def brute_force_tsp(dist: np.ndarray) -> tuple[float, list[int]]:
    n = int(dist.shape[0])
    best_cost = math.inf
    best_tour: list[int] = []
    for perm in itertools.permutations(range(1, n)):
        tour = [0, *perm, 0]
        cost = sum(float(dist[tour[i], tour[i + 1]]) for i in range(len(tour) - 1))
        if cost < best_cost:
            best_cost = cost
            best_tour = tour
    return float(best_cost), best_tour


def brute_force_tw(
    ctx: RoutingContext, task_ids: list[str], courier_id: int
) -> ExactResult:
    """Brute-force permutations for a single route (n <= 8)."""

    start = time.perf_counter()
    best_cost = math.inf
    best_perm: list[str] = []
    for perm in itertools.permutations(task_ids):
        schedule = ctx.schedule_route(courier_id, perm)
        if schedule.feasible and schedule.distance_m < best_cost:
            best_cost = schedule.distance_m
            best_perm = list(perm)
    return ExactResult(
        cost=best_cost,
        task_ids=best_perm,
        proven=True,
        runtime_s=time.perf_counter() - start,
        method="brute_force_tw",
    )


def branch_and_bound_tw(
    ctx: RoutingContext,
    task_ids: list[str],
    courier_id: int,
    time_limit_s: float = 10.0,
) -> ExactResult:
    """Depth-first branch-and-bound for one route with hard time windows."""

    start = time.perf_counter()
    courier = ctx.courier_by_id[courier_id]
    best_cost = math.inf
    best_perm: list[str] = []
    proven = True
    timed_out = False

    def lower_bound(current_node: int, distance_so_far: float) -> float:
        return distance_so_far + float(ctx.dist[current_node, 0])

    def dfs(
        remaining: set[str],
        route: list[str],
        current_time: float,
        current_node: int,
        distance_so_far: float,
        load: int,
        weight: float,
    ) -> None:
        nonlocal best_cost, best_perm, proven, timed_out
        if timed_out:
            return
        if time.perf_counter() - start > time_limit_s:
            proven = False
            timed_out = True
            return
        if lower_bound(current_node, distance_so_far) >= best_cost - 1e-9:
            return
        if not remaining:
            back_m = float(ctx.dist[current_node, 0])
            end_time = current_time + back_m / courier.speed_mps / 60.0
            if end_time <= ctx.shift_end + 1e-9 and distance_so_far + back_m < best_cost:
                best_cost = distance_so_far + back_m
                best_perm = list(route)
            return
        ordered = sorted(
            remaining,
            key=lambda tid: (
                ctx.tasks[tid].window.end_min,
                -ctx.tasks[tid].priority_score,
                tid,
            ),
        )
        for tid in ordered:
            task = ctx.tasks[tid]
            node = ctx.task_node(tid)
            travel = float(ctx.dist[current_node, node])
            arrival = current_time + travel / courier.speed_mps / 60.0
            if arrival > task.window.end_min + 1e-9:
                continue
            if arrival < task.window.start_min:
                arrival = task.window.start_min
            new_load = load + task.demand
            new_weight = weight + task.weight_kg
            if new_load > courier.capacity_packages:
                continue
            if new_weight > courier.capacity_kg + 1e-9:
                continue
            new_time = arrival + task.service_s / 60.0
            back_m = float(ctx.dist[node, 0])
            if new_time + back_m / courier.speed_mps / 60.0 > ctx.shift_end + 1e-9:
                continue
            remaining.remove(tid)
            route.append(tid)
            dfs(
                remaining,
                route,
                new_time,
                node,
                distance_so_far + travel,
                new_load,
                new_weight,
            )
            route.pop()
            remaining.add(tid)

    dfs(set(task_ids), [], float(ctx.shift_start), 0, 0.0, 0, 0.0)
    return ExactResult(
        cost=best_cost,
        task_ids=best_perm,
        proven=proven,
        runtime_s=time.perf_counter() - start,
        method="branch_and_bound_tw",
    )
