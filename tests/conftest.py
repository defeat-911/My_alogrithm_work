from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from campus_express.io import load_campus, load_config, load_packages
from campus_express.models import Courier, Priority, Task, TimeWindow
from campus_express.routing.common import RoutingContext

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def campus():
    return load_campus(ROOT / "data" / "campus.json")


@pytest.fixture(scope="session")
def config():
    return load_config(ROOT / "config" / "default.yaml")


@pytest.fixture(scope="session")
def packages_100():
    return load_packages(ROOT / "data" / "packages_100.json")


@pytest.fixture(scope="session")
def packages_500():
    return load_packages(ROOT / "data" / "packages_500.json")


@pytest.fixture
def tiny_ctx():
    """Three tasks with a hand-checkable distance/time structure."""

    tasks = {
        "A": Task(
            id="A",
            point_id="P1",
            window=TimeWindow(480, 500),
            package_ids=("p1",),
            demand=1,
            weight_kg=0.5,
            priority=Priority.NORMAL,
            priority_score=1.0,
            service_s=60.0,
        ),
        "B": Task(
            id="B",
            point_id="P2",
            window=TimeWindow(480, 500),
            package_ids=("p2",),
            demand=1,
            weight_kg=0.5,
            priority=Priority.URGENT,
            priority_score=2.0,
            service_s=60.0,
        ),
        "C": Task(
            id="C",
            point_id="P3",
            window=TimeWindow(480, 490),
            package_ids=("p3",),
            demand=1,
            weight_kg=0.5,
            priority=Priority.EXPRESS,
            priority_score=3.0,
            service_s=60.0,
        ),
    }
    dist = np.array(
        [
            [0.0, 600.0, 600.0, 600.0],
            [600.0, 0.0, 300.0, 300.0],
            [600.0, 300.0, 0.0, 300.0],
            [600.0, 300.0, 300.0, 0.0],
        ]
    )
    return RoutingContext(
        tasks=tasks,
        task_order=["A", "B", "C"],
        point_index={"P1": 1, "P2": 2, "P3": 3},
        dist=dist,
        couriers=[Courier(0, 10, 10.0, 1.0, 480, 1080)],
        shift_start=480,
        shift_end=1080,
        hard_windows=True,
    )
