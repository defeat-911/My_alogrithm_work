"""Intra-route and inter-route local search for VRPTW solutions."""

from __future__ import annotations

from copy import deepcopy

from ..models import Solution
from .common import RoutingContext


def _copy_solution(solution: Solution) -> Solution:
    return Solution(
        routes=[
            type(route)(route.courier_id, list(route.task_ids))
            for route in solution.routes
        ],
        unassigned=list(solution.unassigned),
        metrics=dict(solution.metrics),
    )


def two_opt_route(
    ctx: RoutingContext, courier_id: int, task_ids: list[str]
) -> tuple[list[str], float]:
    """2-opt within one route, returning the best feasible route."""

    best = list(task_ids)
    best_schedule = ctx.schedule_route(courier_id, best)
    if len(best) < 3 or not best_schedule.feasible:
        return best, best_schedule.distance_m
    improved = True
    while improved:
        improved = False
        n = len(best)
        for i in range(n - 1):
            for j in range(i + 1, n):
                cand = best[:i] + list(reversed(best[i : j + 1])) + best[j + 1 :]
                schedule = ctx.schedule_route(courier_id, cand)
                if (
                    schedule.feasible
                    and schedule.distance_m < best_schedule.distance_m - 1e-6
                ):
                    best = cand
                    best_schedule = schedule
                    improved = True
                    break
            if improved:
                break
    return best, best_schedule.distance_m


def or_opt_route(
    ctx: RoutingContext, courier_id: int, task_ids: list[str], max_segment: int = 3
) -> tuple[list[str], float]:
    """Move a segment of 1--3 consecutive tasks to another position."""

    best = list(task_ids)
    best_schedule = ctx.schedule_route(courier_id, best)
    if len(best) < 2 or not best_schedule.feasible:
        return best, best_schedule.distance_m
    improved = True
    while improved:
        improved = False
        n = len(best)
        for length in range(1, min(max_segment, n - 1) + 1):
            for start in range(0, n - length + 1):
                segment = best[start : start + length]
                rest = best[:start] + best[start + length :]
                for pos in range(len(rest) + 1):
                    if pos == start:
                        continue
                    cand = rest[:pos] + segment + rest[pos:]
                    schedule = ctx.schedule_route(courier_id, cand)
                    if (
                        schedule.feasible
                        and schedule.distance_m < best_schedule.distance_m - 1e-6
                    ):
                        best = cand
                        best_schedule = schedule
                        improved = True
                        break
                if improved:
                    break
            if improved:
                break
    return best, best_schedule.distance_m


def polish_routes(ctx: RoutingContext, solution: Solution) -> Solution:
    """Apply 2-opt then Or-opt to every route."""

    result = _copy_solution(solution)
    for route in result.routes:
        route.task_ids, _ = two_opt_route(ctx, route.courier_id, route.task_ids)
        route.task_ids, _ = or_opt_route(ctx, route.courier_id, route.task_ids)
    return ctx.evaluate(result)


def relocate(ctx: RoutingContext, solution: Solution, max_moves: int = 200) -> Solution:
    """Move one task to the cheapest feasible position in another route."""

    best = _copy_solution(solution)
    best = ctx.evaluate(best)
    if best.metrics.get("feasible", 0.0) < 1.0:
        return best
    for _ in range(max_moves):
        improved = False
        for a in range(len(best.routes)):
            for i, tid in enumerate(list(best.routes[a].task_ids)):
                for b in range(len(best.routes)):
                    if a == b:
                        continue
                    for pos in range(len(best.routes[b].task_ids) + 1):
                        cand = _copy_solution(best)
                        cand.routes[a].task_ids.pop(i)
                        cand.routes[b].task_ids.insert(pos, tid)
                        cand = ctx.evaluate(cand)
                        if (
                            cand.metrics.get("feasible", 0.0) == 1.0
                            and cand.metrics["objective"]
                            < best.metrics["objective"] - 1e-6
                        ):
                            best = cand
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return best


def swap(ctx: RoutingContext, solution: Solution, max_moves: int = 200) -> Solution:
    """Swap two tasks between different routes."""

    best = _copy_solution(solution)
    best = ctx.evaluate(best)
    if best.metrics.get("feasible", 0.0) < 1.0:
        return best
    for _ in range(max_moves):
        improved = False
        for a in range(len(best.routes)):
            for b in range(a + 1, len(best.routes)):
                for i in range(len(best.routes[a].task_ids)):
                    for j in range(len(best.routes[b].task_ids)):
                        cand = _copy_solution(best)
                        ta = cand.routes[a].task_ids[i]
                        tb = cand.routes[b].task_ids[j]
                        cand.routes[a].task_ids[i] = tb
                        cand.routes[b].task_ids[j] = ta
                        cand = ctx.evaluate(cand)
                        if (
                            cand.metrics.get("feasible", 0.0) == 1.0
                            and cand.metrics["objective"]
                            < best.metrics["objective"] - 1e-6
                        ):
                            best = cand
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break
        if not improved:
            break
    return best


def improve(
    ctx: RoutingContext,
    solution: Solution,
    max_rounds: int = 20,
    use_inter_route: bool = True,
) -> Solution:
    """Polish a solution with 2-opt/Or-opt and optional inter-route moves."""

    best = polish_routes(ctx, solution)
    for _ in range(max_rounds):
        before = best.metrics.get("objective", float("inf"))
        if use_inter_route:
            best = relocate(ctx, best)
            best = swap(ctx, best)
        best = polish_routes(ctx, best)
        if best.metrics.get("objective", float("inf")) >= before - 1e-6:
            break
    return ctx.evaluate(best)
