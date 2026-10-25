"""Construction baselines: nearest-neighbour/EDD and cheapest insertion."""

from __future__ import annotations

from typing import Sequence

from ..models import Route, Solution
from .common import RoutingContext


def _task_urgency(ctx: RoutingContext, task_id: str) -> tuple[float, float, float, str]:
    task = ctx.tasks[task_id]
    return (task.window.end_min, -task.priority_score, task.window.start_min, task.id)


def nn_edd(ctx: RoutingContext) -> Solution:
    """Greedy nearest-neighbour with earliest-deadline-first tie-breaking.

    Tasks are appended to the current courier's route; a task is only accepted
    if the resulting route remains feasible.  When a courier cannot take any
    more tasks, the next courier starts.
    """

    unassigned = set(ctx.task_order)
    routes: list[list[str]] = [[] for _ in ctx.couriers]
    for courier in ctx.couriers:
        route = routes[courier.id]
        while unassigned:
            current_schedule = ctx.schedule_route(courier.id, route)
            candidates = []
            for tid in sorted(unassigned, key=lambda t: _task_urgency(ctx, t)):
                cand_schedule = ctx.schedule_route(courier.id, route + [tid])
                if not cand_schedule.feasible:
                    continue
                delta = cand_schedule.distance_m - current_schedule.distance_m
                candidates.append(
                    (
                        ctx.tasks[tid].window.end_min,
                        delta,
                        -ctx.tasks[tid].priority_score,
                        tid,
                    )
                )
            if not candidates:
                break
            candidates.sort()
            chosen = candidates[0][3]
            route.append(chosen)
            unassigned.remove(chosen)
    solution = Solution(
        routes=[Route(c.id, routes[c.id]) for c in ctx.couriers],
        unassigned=sorted(unassigned),
    )
    return ctx.evaluate(solution)


def cheapest_insertion(ctx: RoutingContext) -> Solution:
    """Insert the most urgent tasks first at their cheapest feasible position."""

    routes: list[list[str]] = [[] for _ in ctx.couriers]
    unassigned = set(ctx.task_order)
    order = sorted(unassigned, key=lambda t: _task_urgency(ctx, t))
    for tid in order:
        best: tuple[float, int, int] | None = None
        for courier in ctx.couriers:
            route = routes[courier.id]
            base = ctx.schedule_route(courier.id, route)
            for pos in range(len(route) + 1):
                cand = route[:pos] + [tid] + route[pos:]
                schedule = ctx.schedule_route(courier.id, cand)
                if not schedule.feasible:
                    continue
                delta = schedule.distance_m - base.distance_m
                key = (delta, courier.id, pos)
                if best is None or key < best:
                    best = key
        if best is not None:
            _, courier_id, pos = best
            routes[courier_id] = (
                routes[courier_id][:pos] + [tid] + routes[courier_id][pos:]
            )
            unassigned.remove(tid)
    solution = Solution(
        routes=[Route(c.id, routes[c.id]) for c in ctx.couriers],
        unassigned=sorted(unassigned),
    )
    return ctx.evaluate(solution)
