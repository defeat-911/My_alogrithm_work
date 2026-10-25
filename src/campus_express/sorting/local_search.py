"""Local search for capacitated sorting assignments."""

from __future__ import annotations

import time
from typing import Mapping, Sequence

import numpy as np

from ..models import Campus
from .common import (
    Assignment,
    assignment_key,
    evaluate_assignment,
    loads_from_labels,
)
from .kmeans import capacitated_kmeans


def improve_assignment(
    assignment: Assignment,
    campus: Campus,
    dist: np.ndarray,
    point_index: Mapping[str, int],
    demand: Mapping[str, int],
    capacity: int,
    cv_penalty: float = 50.0,
    max_iter: int = 500,
    time_limit_s: float = 5.0,
) -> Assignment:
    """First-improvement relocate/swap search on the sorting objective."""

    best = evaluate_assignment(
        assignment.copy(), campus, dist, point_index, demand, capacity, cv_penalty
    )
    best_key = assignment_key(best, capacity)
    ids = list(best.labels)
    k = best.k
    started = time.perf_counter()
    for _ in range(max_iter):
        if time.perf_counter() - started > time_limit_s:
            break
        improved = False
        loads = loads_from_labels(best.labels, demand, k)
        sizes = [0] * k
        for label in best.labels.values():
            sizes[label] += 1

        # Relocate one point to another cluster.
        for pid in ids:
            a = best.labels[pid]
            if sizes[a] <= 1:
                continue
            for b in range(k):
                if b == a:
                    continue
                if loads[b] + demand[pid] > capacity and loads[a] <= capacity:
                    continue
                cand = best.copy()
                cand.labels[pid] = b
                cand.loads = loads_from_labels(cand.labels, demand, k)
                evaluate_assignment(
                    cand, campus, dist, point_index, demand, capacity, cv_penalty
                )
                key = assignment_key(cand, capacity)
                if key < best_key:
                    best, best_key = cand, key
                    improved = True
                    break
            if improved:
                break
        if improved:
            continue

        # Swap two points in different clusters.
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                pi, pj = ids[i], ids[j]
                a, b = best.labels[pi], best.labels[pj]
                if a == b:
                    continue
                if (
                    loads[a] - demand[pi] + demand[pj] > capacity
                    or loads[b] - demand[pj] + demand[pi] > capacity
                ):
                    continue
                cand = best.copy()
                cand.labels[pi], cand.labels[pj] = b, a
                cand.loads = loads_from_labels(cand.labels, demand, k)
                evaluate_assignment(
                    cand, campus, dist, point_index, demand, capacity, cv_penalty
                )
                key = assignment_key(cand, capacity)
                if key < best_key:
                    best, best_key = cand, key
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break
    return best


def sort_capacitated(
    point_ids: Sequence[str],
    points_xy: Mapping[str, tuple[float, float]],
    demand: Mapping[str, int],
    k: int,
    capacity: int,
    campus: Campus,
    dist: np.ndarray,
    point_index: Mapping[str, int],
    seed: int = 1,
    n_init: int = 10,
    max_iter: int = 100,
    cv_penalty: float = 50.0,
    local_search_time_s: float = 5.0,
) -> Assignment:
    """Capacitated K-Means++ followed by relocate/swap local search."""

    def score(assign: Assignment) -> tuple:
        evaluate_assignment(
            assign, campus, dist, point_index, demand, capacity, cv_penalty
        )
        return assignment_key(assign, capacity)

    initial = capacitated_kmeans(
        point_ids=point_ids,
        points_xy=points_xy,
        demand=demand,
        k=k,
        capacity=capacity,
        seed=seed,
        n_init=n_init,
        max_iter=max_iter,
        score_fn=score,
    )
    return improve_assignment(
        initial,
        campus,
        dist,
        point_index,
        demand,
        capacity,
        cv_penalty=cv_penalty,
        time_limit_s=local_search_time_s,
    )
