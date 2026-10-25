"""Small reusable helpers shared by sorting and routing."""

from __future__ import annotations

from typing import Sequence

import numpy as np


def tour_length(tour: Sequence[int], dist: np.ndarray) -> float:
    if len(tour) < 2:
        return 0.0
    return float(sum(dist[tour[i], tour[i + 1]] for i in range(len(tour) - 1)))


def nearest_neighbor_tour(
    nodes: Sequence[int], dist: np.ndarray, start: int = 0
) -> list[int]:
    """Build a closed tour through ``nodes`` starting and ending at ``start``."""

    remaining = [n for n in nodes if n != start]
    tour = [start]
    current = start
    while remaining:
        nxt = min(remaining, key=lambda n: (dist[current, n], n))
        tour.append(nxt)
        remaining.remove(nxt)
        current = nxt
    tour.append(start)
    return tour


def two_opt_tour(
    tour: Sequence[int], dist: np.ndarray, max_passes: int = 20
) -> list[int]:
    """Classic 2-opt for a closed tour whose first and last nodes are fixed."""

    best = list(tour)
    if len(best) < 5:
        return best
    for _ in range(max_passes):
        improved = False
        for i in range(1, len(best) - 2):
            for j in range(i + 1, len(best) - 1):
                a, b = best[i - 1], best[i]
                c, d = best[j], best[j + 1]
                delta = dist[a, c] + dist[b, d] - dist[a, b] - dist[c, d]
                if delta < -1e-9:
                    best[i : j + 1] = reversed(best[i : j + 1])
                    improved = True
        if not improved:
            break
    return best


def tsp_proxy(
    cluster_point_ids: Sequence[str],
    point_index: dict[str, int],
    dist: np.ndarray,
    depot_index: int = 0,
) -> float:
    """Nearest-neighbour + 2-opt tour length for one cluster (depot included)."""

    if not cluster_point_ids:
        return 0.0
    nodes = [depot_index] + [point_index[p] for p in cluster_point_ids]
    tour = nearest_neighbor_tour(nodes, dist, start=depot_index)
    tour = two_opt_tour(tour, dist)
    return tour_length(tour, dist)


def mean_pairwise_distance(indices: Sequence[int], dist: np.ndarray) -> float:
    if len(indices) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(indices)):
        for j in range(i + 1, len(indices)):
            total += dist[indices[i], indices[j]]
            count += 1
    return total / count
