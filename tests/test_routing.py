from __future__ import annotations

import math

import pytest

from campus_express.models import Courier
from campus_express.routing.alns import ALNSParams, alns
from campus_express.routing.baselines import cheapest_insertion, nn_edd
from campus_express.routing.local_search import polish_routes
from campus_express.routing.savings import clarke_wright
from campus_express.solver import build_context, solve_routing


def test_schedule_empty_route(tiny_ctx):
    schedule = tiny_ctx.schedule_route(0, [])
    assert schedule.feasible
    assert schedule.distance_m == 0
    assert schedule.end_time == tiny_ctx.shift_start


def test_schedule_waits_and_returns(tiny_ctx):
    schedule = tiny_ctx.schedule_route(0, ["A"])
    # depot -> A is 600 m at 1 m/s = 10 min; window starts at 480.
    assert math.isclose(schedule.arrivals["A"], 490.0, abs_tol=1e-6)
    assert schedule.waits["A"] == 0
    # 1 min service + 10 min return
    assert math.isclose(schedule.end_time, 501.0, abs_tol=1e-6)
    assert schedule.feasible


def test_hard_time_window_infeasible(tiny_ctx):
    schedule = tiny_ctx.schedule_route(0, ["A", "C"])
    assert schedule.tardiness_min > 0
    assert not schedule.feasible


def test_soft_time_window_tracks_tardiness(tiny_ctx):
    from campus_express.routing.common import RoutingContext

    soft = RoutingContext(
        tasks=tiny_ctx.tasks,
        task_order=tiny_ctx.task_order,
        point_index=tiny_ctx.point_index,
        dist=tiny_ctx.dist,
        couriers=tiny_ctx.couriers,
        shift_start=tiny_ctx.shift_start,
        shift_end=tiny_ctx.shift_end,
        hard_windows=False,
    )
    schedule = soft.schedule_route(0, ["A", "C"])
    assert schedule.feasible
    assert schedule.tardiness_min > 0
    assert schedule.tardiness_min == pytest.approx(6.0, abs=1e-6)


def test_capacity_infeasible(tiny_ctx):
    from dataclasses import replace

    tight = replace(tiny_ctx.couriers[0], capacity_packages=0)
    from campus_express.routing.common import RoutingContext

    ctx = RoutingContext(
        tasks=tiny_ctx.tasks,
        task_order=tiny_ctx.task_order,
        point_index=tiny_ctx.point_index,
        dist=tiny_ctx.dist,
        couriers=[tight],
        shift_start=tiny_ctx.shift_start,
        shift_end=tiny_ctx.shift_end,
        hard_windows=True,
    )
    schedule = ctx.schedule_route(0, ["A"])
    assert not schedule.feasible
    assert "capacity_packages" in schedule.reasons


def test_baselines_are_feasible_and_serve_all():
    ctx = build_context(packages_path="data/packages_100.json")
    for solver in (nn_edd, cheapest_insertion, clarke_wright):
        solution = solver(ctx.routing)
        assert solution.metrics["feasible"] == 1.0
        assert solution.metrics["unassigned"] == 0
        assert solution.metrics["n_tasks"] == len(ctx.tasks)
        assert solution.metrics["on_time_rate"] == 1.0


def test_savings_plus_two_opt_improves_distance():
    ctx = build_context(packages_path="data/packages_100.json")
    raw = clarke_wright(ctx.routing)
    polished = polish_routes(ctx.routing, raw)
    assert polished.metrics["feasible"] == 1.0
    assert polished.metrics["distance_m"] <= raw.metrics["distance_m"] + 1e-6


def test_alns_quick_is_feasible_and_serves_all():
    ctx = build_context(packages_path="data/packages_100.json")
    initial = polish_routes(ctx.routing, clarke_wright(ctx.routing))
    result = alns(
        ctx.routing,
        initial,
        ALNSParams(iterations=15, time_limit_s=2.0, seed=1),
    )
    assert result.best.metrics["feasible"] == 1.0
    assert result.best.metrics["unassigned"] == 0
    assert result.best.metrics["distance_m"] <= initial.metrics["distance_m"] * 1.05


def test_routing_deterministic():
    ctx = build_context(packages_path="data/packages_100.json")
    a = nn_edd(ctx.routing)
    b = nn_edd(ctx.routing)
    assert a.metrics["distance_m"] == pytest.approx(b.metrics["distance_m"])
    assert [r.task_ids for r in a.routes] == [r.task_ids for r in b.routes]
