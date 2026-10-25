from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from campus_express.models import Courier, Task, TimeWindow
from campus_express.routing.common import RoutingContext
from campus_express.routing.exact import (
    branch_and_bound_tw,
    brute_force_tsp,
    brute_force_tw,
    held_karp,
)


def _random_matrix(n: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    points = rng.uniform(0, 100, size=(n, 2))
    diff = points[:, None, :] - points[None, :, :]
    return np.sqrt((diff**2).sum(axis=2))


def test_held_karp_matches_brute_force():
    for n in range(5, 9):
        for seed in range(5):
            dist = _random_matrix(n, seed)
            cost_hk, _ = held_karp(dist)
            cost_bf, _ = brute_force_tsp(dist)
            assert math.isclose(cost_hk, cost_bf, rel_tol=1e-9, abs_tol=1e-9)


def test_held_karp_known_square():
    dist = np.array(
        [
            [0.0, 1.0, math.sqrt(2), 1.0],
            [1.0, 0.0, 1.0, math.sqrt(2)],
            [math.sqrt(2), 1.0, 0.0, 1.0],
            [1.0, math.sqrt(2), 1.0, 0.0],
        ]
    )
    cost, tour = held_karp(dist)
    assert math.isclose(cost, 4.0, abs_tol=1e-9)
    assert tour[0] == 0 and tour[-1] == 0
    assert sorted(tour[1:-1]) == [1, 2, 3]


def _tw_context(n: int = 5) -> RoutingContext:
    rng = np.random.default_rng(42)
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
            priority=1,
            priority_score=1.0,
            service_s=60.0,
        )
    point_index = {f"P{i}": i for i in range(1, n + 1)}
    return RoutingContext(
        tasks=tasks,
        task_order=list(tasks),
        point_index=point_index,
        dist=dist,
        couriers=[Courier(0, 20, 20.0, 1.0, 480, 1080)],
        shift_start=480,
        shift_end=1080,
        hard_windows=True,
    )


def test_brute_force_and_branch_and_bound_match():
    ctx = _tw_context(5)
    bf = brute_force_tw(ctx, ctx.task_order, 0)
    bb = branch_and_bound_tw(ctx, ctx.task_order, 0, time_limit_s=10.0)
    assert bf.proven and bb.proven
    assert math.isclose(bf.cost, bb.cost, rel_tol=1e-9, abs_tol=1e-9)
    assert sorted(bf.task_ids) == sorted(ctx.task_order)
    assert sorted(bb.task_ids) == sorted(ctx.task_order)
