"""Clarke-Wright savings with time-window feasibility and route packing."""

from __future__ import annotations

from ..models import Route, Solution
from .common import RoutingContext


def clarke_wright(ctx: RoutingContext) -> Solution:
    """Classic savings construction followed by courier packing.

    Savings merges singleton routes while the merged route remains feasible.
    The resulting route pool is then packed into the available couriers; if a
    route cannot be packed as a whole, its tasks are inserted one by one at the
    cheapest feasible position.
    """

    task_ids = list(ctx.task_order)
    routes: dict[str, list[str]] = {tid: [tid] for tid in task_ids}
    route_of: dict[str, str] = {tid: tid for tid in task_ids}

    savings: list[tuple[float, str, str]] = []
    for i in task_ids:
        ni = ctx.task_node(i)
        for j in task_ids:
            if i == j:
                continue
            nj = ctx.task_node(j)
            s = (
                float(ctx.dist[0, ni])
                + float(ctx.dist[0, nj])
                - float(ctx.dist[ni, nj])
            )
            if s > 1e-9:
                savings.append((s, i, j))
    savings.sort(key=lambda x: (-x[0], x[1], x[2]))

    for _, i, j in savings:
        ri, rj = route_of[i], route_of[j]
        if ri == rj:
            continue
        ri_tasks, rj_tasks = routes[ri], routes[rj]
        if ri_tasks[-1] == i and rj_tasks[0] == j:
            merged = ri_tasks + rj_tasks
        elif rj_tasks[-1] == i and ri_tasks[0] == j:
            ri, rj = rj, ri
            ri_tasks, rj_tasks = rj_tasks, ri_tasks
            merged = ri_tasks + rj_tasks
        else:
            continue
        if not ctx.schedule_route(ctx.couriers[0].id, merged).feasible:
            continue
        routes[ri] = merged
        del routes[rj]
        for tid in merged:
            route_of[tid] = ri

    route_pool = sorted(
        routes.values(),
        key=lambda r: (-sum(ctx.tasks[t].demand for t in r), -len(r), r[0]),
    )
    courier_routes: list[list[str]] = [[] for _ in ctx.couriers]

    def route_cost(courier_id: int, route: list[str]) -> float:
        return ctx.schedule_route(courier_id, route).distance_m

    for route in route_pool:
        placed = False
        for courier in ctx.couriers:
            cand = courier_routes[courier.id] + route
            if ctx.schedule_route(courier.id, cand).feasible:
                courier_routes[courier.id] = cand
                placed = True
                break
        if placed:
            continue
        # Fall back to inserting the route's tasks one by one.
        for tid in route:
            best: tuple[float, int, int] | None = None
            for courier in ctx.couriers:
                base = route_cost(courier.id, courier_routes[courier.id])
                for pos in range(len(courier_routes[courier.id]) + 1):
                    cand = (
                        courier_routes[courier.id][:pos]
                        + [tid]
                        + courier_routes[courier.id][pos:]
                    )
                    schedule = ctx.schedule_route(courier.id, cand)
                    if not schedule.feasible:
                        continue
                    delta = schedule.distance_m - base
                    key = (delta, courier.id, pos)
                    if best is None or key < best:
                        best = key
            if best is not None:
                _, cid, pos = best
                courier_routes[cid] = (
                    courier_routes[cid][:pos] + [tid] + courier_routes[cid][pos:]
                )

    assigned = {tid for route in courier_routes for tid in route}
    solution = Solution(
        routes=[Route(c.id, courier_routes[c.id]) for c in ctx.couriers],
        unassigned=sorted(set(task_ids) - assigned),
    )
    return ctx.evaluate(solution)
