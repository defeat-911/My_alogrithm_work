from __future__ import annotations

from dataclasses import replace

import pytest

from campus_express.data_gen import (
    aggregate_tasks,
    check_instance,
    generate_packages,
)
from campus_express.models import Package, Priority, TimeWindow
from campus_express.routing.common import RoutingContext
from campus_express.solver import build_context


def test_single_package(campus, config):
    packages = generate_packages(campus, 1, 1, config)
    assert len(packages) == 1
    tasks = aggregate_tasks(packages, campus, config)
    assert len(tasks) == 1
    assert check_instance(packages, campus, config)["feasible"]


def test_empty_instance_is_infeasible(campus, config):
    report = check_instance([], campus, config)
    assert not report["feasible"]
    assert "empty package list" in report["reasons"]


def test_aggregate_empty_raises(campus, config):
    with pytest.raises(ValueError):
        aggregate_tasks([], campus, config)


def test_single_point_aggregation(campus, config):
    packages = [
        Package(
            id=f"P{i}",
            dest_id="D01",
            weight_kg=0.5,
            priority=Priority.NORMAL,
            window=TimeWindow(480, 600),
            bucket=0,
        )
        for i in range(3)
    ]
    tasks = aggregate_tasks(packages, campus, config)
    assert len(tasks) == 1
    assert tasks[0].demand == 3
    assert tasks[0].service_s == 60 + 20 * 3


def test_single_point_over_capacity(campus, config):
    packages = [
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
    report = check_instance(packages, campus, config)
    assert not report["feasible"]
    assert any("single point demand" in reason for reason in report["reasons"])


def test_one_courier_does_not_crash():
    ctx = build_context(
        packages_path="data/packages_100.json",
        couriers_count=1,
    )
    from campus_express.routing.savings import clarke_wright

    solution = clarke_wright(ctx.routing)
    assert solution.metrics["n_tasks"] == len(ctx.tasks)
    served = sum(len(route.task_ids) for route in solution.routes)
    assert served + len(solution.unassigned) == len(ctx.tasks)


def test_capacity_exact_boundary(tiny_ctx):
    exact = replace(tiny_ctx.couriers[0], capacity_packages=2)
    ctx = RoutingContext(
        tasks=tiny_ctx.tasks,
        task_order=tiny_ctx.task_order,
        point_index=tiny_ctx.point_index,
        dist=tiny_ctx.dist,
        couriers=[exact],
        shift_start=tiny_ctx.shift_start,
        shift_end=tiny_ctx.shift_end,
        hard_windows=True,
    )
    assert ctx.schedule_route(0, ["A", "B"]).feasible
    over = ctx.schedule_route(0, ["A", "B", "C"])
    assert not over.feasible
    assert "capacity_packages" in over.reasons
