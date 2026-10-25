from __future__ import annotations

import pytest

from campus_express.data_gen import (
    aggregate_tasks,
    check_instance,
    generate_packages,
)
from campus_express.io import validate_packages
from campus_express.models import Package, Priority, TimeWindow, format_hhmm, parse_hhmm


def test_time_parse_and_format():
    assert parse_hhmm("08:30") == 510
    assert format_hhmm(510) == "08:30"
    with pytest.raises(ValueError):
        parse_hhmm("25:00")
    with pytest.raises(ValueError):
        TimeWindow(600, 500)


def test_load_and_validate_packages(campus, packages_100):
    validate_packages(packages_100, campus)
    assert len(packages_100) == 100
    assert all(p.dest_id in campus.points for p in packages_100)


def test_validate_rejects_unknown_destination(campus, packages_100):
    bad = list(packages_100)
    bad[0] = Package(
        id=bad[0].id,
        dest_id="NOPE",
        weight_kg=bad[0].weight_kg,
        priority=bad[0].priority,
        window=bad[0].window,
        bucket=bad[0].bucket,
    )
    with pytest.raises(ValueError):
        validate_packages(bad, campus)


def test_aggregate_tasks_conserves_packages(campus, config, packages_500):
    tasks = aggregate_tasks(packages_500, campus, config)
    ids = [pid for task in tasks for pid in task.package_ids]
    assert len(ids) == len(packages_500)
    assert len(ids) == len(set(ids))
    assert sum(task.demand for task in tasks) == len(packages_500)
    assert 60 <= len(tasks) <= 120


def test_generation_is_deterministic(campus, config):
    a = generate_packages(campus, 100, 7, config)
    b = generate_packages(campus, 100, 7, config)
    assert [(p.id, p.dest_id, int(p.priority)) for p in a] == [
        (p.id, p.dest_id, int(p.priority)) for p in b
    ]


def test_generation_rejects_zero(campus, config):
    with pytest.raises(ValueError):
        generate_packages(campus, 0, 1, config)


def test_feasibility_report(campus, config, packages_500):
    report = check_instance(packages_500, campus, config)
    assert report["feasible"]
    assert report["max_point_demand"] <= 60
    assert report["total_weight_kg"] <= 0.95 * report["courier_capacity_kg"]


def test_empty_tasks_raise(campus, config):
    with pytest.raises(ValueError):
        aggregate_tasks([], campus, config)
