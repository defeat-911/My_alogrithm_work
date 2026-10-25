"""Minimal adaptive large neighbourhood search for the campus VRPTW."""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from ..models import Solution
from .common import RoutingContext


@dataclass
class ALNSParams:
    iterations: int = 2000
    destroy_fraction: float = 0.15
    min_remove: int = 2
    max_remove: int = 15
    t0_ratio: float = 0.05
    tend_ratio: float = 0.001
    segment: int = 100
    reaction: float = 0.2
    seed: int = 1
    time_limit_s: float = 30.0


@dataclass
class ALNSResult:
    best: Solution
    convergence: list[float]
    runtime_s: float
    iterations: int
    operator_stats: dict[str, float] = field(default_factory=dict)


def _copy(solution: Solution) -> Solution:
    return Solution(
        routes=[
            type(route)(route.courier_id, list(route.task_ids))
            for route in solution.routes
        ],
        unassigned=list(solution.unassigned),
        metrics=dict(solution.metrics),
    )


def _all_assigned(solution: Solution) -> list[str]:
    return [tid for route in solution.routes for tid in route.task_ids]


def _base_distances(ctx: RoutingContext, solution: Solution) -> dict[int, float]:
    return {
        route.courier_id: ctx.schedule_route(route.courier_id, route.task_ids).distance_m
        for route in solution.routes
    }


def insertion_options(
    ctx: RoutingContext, solution: Solution, task_id: str
) -> list[tuple[float, int, int]]:
    """All feasible ``(distance_delta, courier_id, position)`` insertions."""

    options: list[tuple[float, int, int]] = []
    base = _base_distances(ctx, solution)
    for route in solution.routes:
        for pos in range(len(route.task_ids) + 1):
            cand = route.task_ids[:pos] + [task_id] + route.task_ids[pos:]
            schedule = ctx.schedule_route(route.courier_id, cand)
            if not schedule.feasible:
                continue
            delta = schedule.distance_m - base.get(route.courier_id, 0.0)
            options.append((delta, route.courier_id, pos))
    options.sort()
    return options


def _apply_insertion(
    solution: Solution, task_id: str, courier_id: int, pos: int
) -> None:
    for route in solution.routes:
        if route.courier_id == courier_id:
            route.task_ids.insert(pos, task_id)
            return
    raise KeyError(courier_id)


def repair_unassigned(ctx: RoutingContext, solution: Solution) -> Solution:
    """Insert unassigned tasks at their cheapest feasible positions."""

    result = _copy(solution)
    pending = sorted(
        result.unassigned,
        key=lambda t: (
            ctx.tasks[t].window.end_min,
            -ctx.tasks[t].priority_score,
            t,
        ),
    )
    result.unassigned = []
    for tid in pending:
        options = insertion_options(ctx, result, tid)
        if not options:
            result.unassigned.append(tid)
            continue
        _, courier_id, pos = options[0]
        _apply_insertion(result, tid, courier_id, pos)
    return ctx.evaluate(result)


def _remove_tasks(solution: Solution, task_ids: list[str]) -> Solution:
    result = _copy(solution)
    remove = set(task_ids)
    for route in result.routes:
        route.task_ids = [tid for tid in route.task_ids if tid not in remove]
    result.unassigned = sorted(set(result.unassigned) | remove)
    return result


def random_removal(
    ctx: RoutingContext, solution: Solution, q: int, rng: random.Random
) -> tuple[Solution, list[str]]:
    assigned = _all_assigned(solution)
    q = min(q, len(assigned))
    removed = rng.sample(assigned, q) if q else []
    return _remove_tasks(solution, removed), removed


def shaw_removal(
    ctx: RoutingContext, solution: Solution, q: int, rng: random.Random
) -> tuple[Solution, list[str]]:
    assigned = _all_assigned(solution)
    if not assigned:
        return _copy(solution), []
    q = min(q, len(assigned))
    seed = rng.choice(assigned)
    seed_task = ctx.tasks[seed]
    seed_node = ctx.task_node(seed)
    finite = [float(ctx.dist[i, j]) for i in range(ctx.dist.shape[0]) for j in range(ctx.dist.shape[1]) if math.isfinite(float(ctx.dist[i, j]))]
    max_dist = max(finite) if finite else 1.0
    horizon = max(1, ctx.shift_end - ctx.shift_start)
    scored = []
    for tid in assigned:
        task = ctx.tasks[tid]
        rel = (
            0.65 * float(ctx.dist[seed_node, ctx.task_node(tid)]) / max_dist
            + 0.25 * abs(task.window.start_min - seed_task.window.start_min) / horizon
            + 0.10 * abs(task.priority_score - seed_task.priority_score) / 2.0
        )
        scored.append((rel, tid))
    scored.sort()
    # A little randomness: sample from the top 2q related tasks.
    pool = [tid for _, tid in scored[: max(q, min(len(scored), 2 * q))]]
    removed = rng.sample(pool, q)
    return _remove_tasks(solution, removed), removed


def greedy_insertion(
    ctx: RoutingContext,
    solution: Solution,
    removed: list[str],
    rng: random.Random,
) -> Solution:
    result = _copy(solution)
    result.unassigned = []
    order = sorted(
        removed,
        key=lambda t: (
            ctx.tasks[t].window.end_min,
            -ctx.tasks[t].priority_score,
            t,
        ),
    )
    for tid in order:
        options = insertion_options(ctx, result, tid)
        if not options:
            result.unassigned.append(tid)
            continue
        _, courier_id, pos = options[0]
        _apply_insertion(result, tid, courier_id, pos)
    return ctx.evaluate(result)


def regret2_insertion(
    ctx: RoutingContext,
    solution: Solution,
    removed: list[str],
    rng: random.Random,
) -> Solution:
    result = _copy(solution)
    result.unassigned = []
    pending = list(removed)
    while pending:
        choice = None
        for tid in pending:
            options = insertion_options(ctx, result, tid)
            if not options:
                continue
            best = options[0]
            regret = (options[1][0] - best[0]) if len(options) > 1 else 1e9
            key = (regret, -ctx.tasks[tid].priority_score, tid)
            if choice is None or key > choice[0]:
                choice = (key, tid, best)
        if choice is None:
            result.unassigned.extend(pending)
            break
        _, tid, best = choice
        _, courier_id, pos = best
        _apply_insertion(result, tid, courier_id, pos)
        pending.remove(tid)
    return ctx.evaluate(result)


def _roulette(rng: random.Random, weights: list[float]) -> int:
    total = sum(max(0.0, w) for w in weights)
    if total <= 0:
        return rng.randrange(len(weights))
    pick = rng.random() * total
    acc = 0.0
    for i, w in enumerate(weights):
        acc += max(0.0, w)
        if pick <= acc:
            return i
    return len(weights) - 1


def alns(
    ctx: RoutingContext,
    initial: Solution,
    params: ALNSParams | None = None,
) -> ALNSResult:
    params = params or ALNSParams()
    rng = random.Random(params.seed)
    start = time.perf_counter()

    current = repair_unassigned(ctx, initial)
    current = ctx.evaluate(current)
    best = _copy(current)
    best = ctx.evaluate(best)
    initial_obj = max(best.metrics.get("objective", 0.0), 1.0)
    t0 = params.t0_ratio * initial_obj
    tend = params.tend_ratio * initial_obj
    temperature = t0
    cooling = (tend / t0) ** (1.0 / max(1, params.iterations)) if t0 > 0 else 1.0

    destroy_ops = [random_removal, shaw_removal]
    repair_ops = [greedy_insertion, regret2_insertion]
    weights_d = [1.0, 1.0]
    weights_r = [1.0, 1.0]
    scores_d = [0.0, 0.0]
    scores_r = [0.0, 0.0]
    counts_d = [0, 0]
    counts_r = [0, 0]
    convergence: list[float] = []
    n_tasks = len(ctx.task_order)
    q = max(
        params.min_remove,
        min(params.max_remove, int(round(params.destroy_fraction * n_tasks))),
    )

    for it in range(params.iterations):
        if time.perf_counter() - start > params.time_limit_s:
            break
        di = _roulette(rng, weights_d)
        ri = _roulette(rng, weights_r)
        destroyed, removed = destroy_ops[di](ctx, current, q, rng)
        candidate = repair_ops[ri](ctx, destroyed, removed, rng)
        candidate = ctx.evaluate(candidate)
        counts_d[di] += 1
        counts_r[ri] += 1

        feasible = candidate.metrics.get("feasible", 0.0) == 1.0
        cand_obj = candidate.metrics.get("objective", float("inf"))
        cur_obj = current.metrics.get("objective", float("inf"))
        accepted = False
        if feasible:
            if cand_obj < cur_obj - 1e-9:
                current = candidate
                accepted = True
                scores_d[di] += 9.0
                scores_r[ri] += 9.0
            elif temperature > 0 and rng.random() < math.exp(
                -max(0.0, cand_obj - cur_obj) / max(temperature, 1e-9)
            ):
                current = candidate
                accepted = True
                scores_d[di] += 13.0
                scores_r[ri] += 13.0
            if cand_obj < best.metrics.get("objective", float("inf")) - 1e-9:
                best = _copy(candidate)
                scores_d[di] += 20.0
                scores_r[ri] += 20.0
        if not accepted:
            # Keep the operator statistics meaningful: a rejected attempt is a
            # zero-score observation.
            pass

        convergence.append(best.metrics.get("objective", float("inf")))
        temperature *= cooling

        if (it + 1) % params.segment == 0:
            for i in range(2):
                if counts_d[i]:
                    weights_d[i] = max(
                        0.05,
                        (1 - params.reaction) * weights_d[i]
                        + params.reaction * scores_d[i] / counts_d[i],
                    )
                if counts_r[i]:
                    weights_r[i] = max(
                        0.05,
                        (1 - params.reaction) * weights_r[i]
                        + params.reaction * scores_r[i] / counts_r[i],
                    )
            scores_d = [0.0, 0.0]
            scores_r = [0.0, 0.0]
            counts_d = [0, 0]
            counts_r = [0, 0]

    runtime = time.perf_counter() - start
    final = repair_unassigned(ctx, best)
    final = ctx.evaluate(final)
    # Keep the best feasible solution if repair made things worse.
    if final.metrics.get("feasible", 0.0) == 1.0 and final.metrics["objective"] < best.metrics["objective"]:
        best = final
    return ALNSResult(
        best=best,
        convergence=convergence,
        runtime_s=runtime,
        iterations=len(convergence),
        operator_stats={
            "destroy_weights": weights_d,
            "repair_weights": weights_r,
        },
    )
