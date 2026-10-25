"""Naive sorting baselines: grid strips and polar sweep."""

from __future__ import annotations

import math
from typing import Mapping, Sequence

from .common import Assignment, loads_from_labels


def sort_grid(
    point_ids: Sequence[str],
    demand: Mapping[str, int],
    k: int,
    points_xy: Mapping[str, tuple[float, float]],
) -> Assignment:
    """Split points into ``k`` vertical strips with roughly equal counts.

    This is the naive "administrative zone" baseline: it ignores demand,
    capacity and route compactness, so it typically produces very uneven
    chute loads.
    """

    ordered = sorted(point_ids, key=lambda p: (points_xy[p][0], points_xy[p][1], p))
    labels: dict[str, int] = {}
    n = len(ordered)
    for i, pid in enumerate(ordered):
        label = min(k - 1, i * k // max(1, n))
        labels[pid] = label
    loads = loads_from_labels(labels, demand, k)
    return Assignment(labels=labels, loads=loads, k=k)


def sort_sweep(
    point_ids: Sequence[str],
    demand: Mapping[str, int],
    k: int,
    center_xy: tuple[float, float],
    points_xy: Mapping[str, tuple[float, float]],
) -> Assignment:
    """Polar sweep: sort by angle and cut into ``k`` demand-balanced arcs."""

    cx, cy = center_xy
    ordered = sorted(
        point_ids,
        key=lambda p: (
            math.atan2(points_xy[p][1] - cy, points_xy[p][0] - cx),
            math.hypot(points_xy[p][0] - cx, points_xy[p][1] - cy),
            p,
        ),
    )
    total = sum(demand[p] for p in ordered)
    n = len(ordered)
    if k > n:
        raise ValueError(f"k={k} > number of points={n}")
    prefix = [0]
    for pid in ordered:
        prefix.append(prefix[-1] + demand[pid])

    labels: dict[str, int] = {}
    start = 0
    for cluster in range(k):
        if cluster == k - 1:
            end = n
        else:
            target = total * (cluster + 1) / k
            end = start + 1
            # Leave at least one point for each remaining cluster.
            max_end = n - (k - cluster - 1)
            while end < max_end and prefix[end] < target:
                end += 1
            end = max(start + 1, min(end, max_end))
        for pid in ordered[start:end]:
            labels[pid] = cluster
        start = end
    loads = loads_from_labels(labels, demand, k)
    return Assignment(labels=labels, loads=loads, k=k)
