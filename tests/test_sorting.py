from __future__ import annotations

import pytest

from campus_express.graph import RoadNetwork
from campus_express.sorting.baselines import sort_grid, sort_sweep
from campus_express.sorting.common import (
    assignment_key,
    evaluate_assignment,
    loads_from_labels,
)
from campus_express.sorting.kmeans import capacitated_kmeans, kmeanspp
from campus_express.sorting.local_search import improve_assignment, sort_capacitated


def _inputs(campus, packages):
    demand = campus.demand_by_point(packages)
    ids = campus.point_ids
    points_xy = {
        pid: (campus.points[pid].x_m, campus.points[pid].y_m) for pid in ids
    }
    point_index = {pid: i + 1 for i, pid in enumerate(ids)}
    dist = RoadNetwork(campus).distance_matrix(campus.key_node_ids)
    return demand, ids, points_xy, point_index, dist


def test_grid_and_sweep_cover_all_points(campus, packages_500):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_500)
    for assignment in (
        sort_grid(ids, demand, 10, points_xy),
        sort_sweep(ids, demand, 10, (600, 500), points_xy),
    ):
        assert set(assignment.labels) == set(ids)
        assert len(assignment.loads) == 10
        assert sum(assignment.loads) == 500
        assert assignment.empty_clusters() == 0


def test_kmeans_is_deterministic(campus, packages_500):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_500)
    a = kmeanspp(ids, points_xy, demand, 10, seed=3, n_init=5)
    b = kmeanspp(ids, points_xy, demand, 10, seed=3, n_init=5)
    assert a.labels == b.labels


def test_kmeans_rejects_too_many_clusters(campus, packages_100):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_100)
    with pytest.raises(ValueError):
        kmeanspp(ids, points_xy, demand, 100, seed=1, n_init=1)


def test_kmeans_duplicate_coordinates(campus, packages_100):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_100)
    duplicate = {pid: (100.0, 100.0) for pid in ids}
    assignment = kmeanspp(ids, duplicate, demand, 10, seed=1, n_init=2)
    assert set(assignment.labels) == set(ids)
    assert sum(assignment.loads) == 100


def test_capacitated_kmeans_respects_capacity_on_500(campus, packages_500):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_500)
    assignment = capacitated_kmeans(
        ids, points_xy, demand, 10, 60, seed=1, n_init=10
    )
    assert set(assignment.labels) == set(ids)
    assert assignment.overflow(60) == 0
    assert assignment.empty_clusters() == 0


def test_local_search_does_not_worsen_key(campus, packages_500):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_500)
    initial = capacitated_kmeans(
        ids, points_xy, demand, 10, 60, seed=1, n_init=5
    )
    evaluate_assignment(initial, campus, dist, point_index, demand, 60, 5000.0)
    before = assignment_key(initial, 60)
    improved = improve_assignment(
        initial, campus, dist, point_index, demand, 60, cv_penalty=5000.0
    )
    after = assignment_key(improved, 60)
    assert after <= before
    assert improved.overflow(60) == 0
    assert improved.empty_clusters() == 0


def test_full_sorting_pipeline(campus, packages_500):
    demand, ids, points_xy, point_index, dist = _inputs(campus, packages_500)
    assignment = sort_capacitated(
        ids,
        points_xy,
        demand,
        10,
        60,
        campus,
        dist,
        point_index,
        seed=1,
        n_init=10,
        cv_penalty=5000.0,
    )
    assert assignment.overflow(60) == 0
    assert assignment.empty_clusters() == 0
    assert sum(assignment.loads) == 500
    assert assignment.metrics["tsp_proxy_m"] > 0
