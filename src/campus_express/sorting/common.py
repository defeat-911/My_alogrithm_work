"""Assignment container and sorting metrics."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Sequence

import numpy as np

from ..models import Campus
from ..utils import mean_pairwise_distance, tsp_proxy


@dataclass
class Assignment:
    labels: dict[str, int]
    loads: list[int]
    k: int
    metrics: dict[str, float] = field(default_factory=dict)

    def clusters(self) -> list[list[str]]:
        result: list[list[str]] = [[] for _ in range(self.k)]
        for point_id, label in sorted(self.labels.items()):
            result[label].append(point_id)
        return result

    def copy(self) -> "Assignment":
        return Assignment(dict(self.labels), list(self.loads), self.k, dict(self.metrics))

    def overflow(self, capacity: int) -> int:
        return sum(max(0, load - capacity) for load in self.loads)

    def load_cv(self) -> float:
        if not self.loads or mean(self.loads) == 0:
            return 0.0
        return pstdev(self.loads) / mean(self.loads)

    def max_load_ratio(self, capacity: int) -> float:
        return max(self.loads, default=0) / capacity if capacity else 0.0

    def empty_clusters(self) -> int:
        return sum(1 for load in self.loads if load == 0)

    def feasible(self, capacity: int) -> bool:
        return self.overflow(capacity) == 0 and self.empty_clusters() == 0


def loads_from_labels(
    labels: dict[str, int], demand: dict[str, int], k: int
) -> list[int]:
    loads = [0] * k
    for point_id, label in labels.items():
        loads[label] += demand.get(point_id, 0)
    return loads


def silhouette_road(
    labels: dict[str, int],
    point_index: dict[str, int],
    dist: np.ndarray,
) -> float:
    """Simplified silhouette using road-network distances.

    Clusters here are small (about 3 points), so this is reported as an
    auxiliary compactness indicator rather than a primary result.
    """

    by_cluster: dict[int, list[str]] = {}
    for pid, label in labels.items():
        by_cluster.setdefault(label, []).append(pid)
    if len(by_cluster) < 2:
        return 0.0
    scores: list[float] = []
    for pid, label in labels.items():
        own = by_cluster[label]
        if len(own) < 2:
            scores.append(0.0)
            continue
        i = point_index[pid]
        a = mean_pairwise_distance([point_index[p] for p in own], dist)
        # Remove the point itself from its own cluster for a fair a(i).
        if len(own) > 2:
            own_others = [point_index[p] for p in own if p != pid]
            a = mean_pairwise_distance(own_others, dist)
        b_values = []
        for other_label, others in by_cluster.items():
            if other_label == label or not others:
                continue
            b_values.append(mean([dist[i, point_index[p]] for p in others]))
        if not b_values:
            scores.append(0.0)
            continue
        b = min(b_values)
        denom = max(a, b)
        scores.append(0.0 if denom == 0 else (b - a) / denom)
    return float(mean(scores))


def evaluate_assignment(
    assignment: Assignment,
    campus: Campus,
    dist: np.ndarray,
    point_index: dict[str, int],
    demand: dict[str, int],
    capacity: int,
    cv_penalty: float = 50.0,
) -> Assignment:
    clusters = assignment.clusters()
    tsp_total = sum(
        tsp_proxy(cluster, point_index, dist) for cluster in clusters
    )
    silhouette = silhouette_road(assignment.labels, point_index, dist)
    assignment.metrics = {
        "tsp_proxy_m": tsp_total,
        "load_cv": assignment.load_cv(),
        "max_load_ratio": assignment.max_load_ratio(capacity),
        "overflow_packages": float(assignment.overflow(capacity)),
        "empty_clusters": float(assignment.empty_clusters()),
        "silhouette": silhouette,
        "objective": tsp_total + cv_penalty * assignment.load_cv(),
        "n_points": float(len(assignment.labels)),
        "n_packages": float(sum(demand.values())),
    }
    return assignment


def assignment_key(assignment: Assignment, capacity: int) -> tuple[float, ...]:
    """Lexicographic key: non-empty clusters, capacity, compactness, balance."""

    return (
        float(assignment.empty_clusters()),
        float(assignment.overflow(capacity)),
        float(assignment.metrics.get("objective", 0.0)),
        float(assignment.load_cv()),
    )


def labels_for_points(
    point_ids: Sequence[str], cluster_index: Sequence[int]
) -> dict[str, int]:
    return {pid: int(cluster_index[i]) for i, pid in enumerate(point_ids)}
