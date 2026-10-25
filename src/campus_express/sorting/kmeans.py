"""K-Means++ and capacity-aware K-Means for sorting."""

from __future__ import annotations

import math
import random
from typing import Callable, Mapping, Sequence

import numpy as np

from .common import Assignment, loads_from_labels


def _init_kmeanspp(
    coords: np.ndarray,
    k: int,
    rng: random.Random,
    weights: np.ndarray | None = None,
) -> np.ndarray:
    n = coords.shape[0]
    if k > n:
        raise ValueError(f"k={k} > number of points={n}")
    if weights is None:
        weights_arr = np.ones(n, dtype=float)
    else:
        weights_arr = np.asarray(weights, dtype=float)
        weights_arr = np.where(weights_arr > 0, weights_arr, 1e-9)
    probs = weights_arr / weights_arr.sum()
    first = rng.choices(range(n), weights=probs.tolist(), k=1)[0]
    centers = [coords[first].copy()]
    for _ in range(1, k):
        d2 = np.min(
            ((coords[:, None, :] - np.asarray(centers)[None, :, :]) ** 2).sum(axis=2),
            axis=1,
        )
        scores = d2 * weights_arr
        total = float(scores.sum())
        if total <= 1e-12:
            # Duplicate coordinates: fall back to weighted uniform sampling.
            idx = rng.choices(range(n), weights=probs.tolist(), k=1)[0]
        else:
            idx = rng.choices(range(n), weights=(scores / total).tolist(), k=1)[0]
        centers.append(coords[idx].copy())
    return np.asarray(centers)


def _assign_nearest(coords: np.ndarray, centers: np.ndarray) -> np.ndarray:
    d2 = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    return np.argmin(d2, axis=1)


def _update_centers(
    coords: np.ndarray,
    labels: np.ndarray,
    k: int,
    weights: np.ndarray | None,
) -> np.ndarray:
    weights_arr = np.ones(len(coords)) if weights is None else np.asarray(weights, float)
    centers = np.zeros((k, coords.shape[1]), dtype=float)
    for c in range(k):
        mask = labels == c
        if not mask.any():
            # Re-seed an empty cluster with the point farthest from its center.
            d2 = ((coords - centers[labels]) ** 2).sum(axis=1)
            idx = int(np.argmax(d2))
            centers[c] = coords[idx]
            labels[idx] = c
            continue
        w = weights_arr[mask]
        centers[c] = (coords[mask] * w[:, None]).sum(axis=0) / max(w.sum(), 1e-12)
    return centers


def _kmeans_core(
    coords: np.ndarray,
    k: int,
    seed: int,
    weights: np.ndarray | None,
    max_iter: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    rng = random.Random(seed)
    centers = _init_kmeanspp(coords, k, rng, weights)
    labels = np.full(len(coords), -1, dtype=int)
    for _ in range(max_iter):
        new_labels = _assign_nearest(coords, centers)
        centers = _update_centers(coords, new_labels, k, weights)
        if np.array_equal(new_labels, labels):
            labels = new_labels
            break
        labels = new_labels
    # Final assignment after the last centroid update.
    labels = _assign_nearest(coords, centers)
    inertia = float(
        (((coords - centers[labels]) ** 2).sum(axis=1) * (weights if weights is not None else 1.0)).sum()
    )
    return labels, centers, inertia


def kmeanspp(
    point_ids: Sequence[str],
    points_xy: Mapping[str, tuple[float, float]],
    demand: Mapping[str, int],
    k: int,
    seed: int = 1,
    n_init: int = 10,
    max_iter: int = 100,
    weighted: bool = True,
) -> Assignment:
    """Multi-start K-Means++ (optionally demand-weighted)."""

    ids = list(point_ids)
    coords = np.asarray([points_xy[p] for p in ids], dtype=float)
    weights = np.asarray([max(1, demand[p]) for p in ids], dtype=float) if weighted else None
    best: tuple[float, np.ndarray] | None = None
    for restart in range(max(1, n_init)):
        labels, _, inertia = _kmeans_core(
            coords, k, seed + restart, weights, max_iter
        )
        if best is None or inertia < best[0] - 1e-9:
            best = (inertia, labels)
    assert best is not None
    label_map = {pid: int(best[1][i]) for i, pid in enumerate(ids)}
    loads = loads_from_labels(label_map, demand, k)
    return Assignment(labels=label_map, loads=loads, k=k)


def _capacity_aware_assignment(
    coords: np.ndarray,
    centers: np.ndarray,
    demand: np.ndarray,
    capacity: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Assign high-demand points first to the nearest cluster with room."""

    n, k = coords.shape[0], centers.shape[0]
    d2 = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    order = sorted(range(n), key=lambda i: (-demand[i], i))
    labels = np.full(n, -1, dtype=int)
    loads = np.zeros(k, dtype=int)
    for i in order:
        for c in np.argsort(d2[i]):
            if loads[c] + demand[i] <= capacity:
                labels[i] = int(c)
                loads[c] += demand[i]
                break
        if labels[i] < 0:
            c = int(np.argmin(d2[i]))
            labels[i] = c
            loads[c] += demand[i]
    return labels, loads


def _repair_capacity(
    coords: np.ndarray,
    labels: np.ndarray,
    demand: np.ndarray,
    capacity: int,
    k: int,
    max_moves: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """Move small points out of overflowing clusters where possible."""

    labels = labels.copy()
    loads = np.zeros(k, dtype=int)
    for i, c in enumerate(labels):
        loads[c] += demand[i]
    for _ in range(max_moves):
        overflow = [c for c in range(k) if loads[c] > capacity]
        if not overflow:
            break
        moved = False
        for c in overflow:
            members = np.where(labels == c)[0]
            members = sorted(members, key=lambda i: (demand[i], i))
            for i in members:
                spare = [
                    j
                    for j in range(k)
                    if j != c and loads[j] + demand[i] <= capacity
                ]
                if not spare:
                    continue
                d2 = ((coords[i] - coords[spare]) ** 2).sum(axis=1)
                j = int(spare[int(np.argmin(d2))])
                labels[i] = j
                loads[c] -= demand[i]
                loads[j] += demand[i]
                moved = True
                break
            if moved:
                break
        if not moved:
            break
    return labels, loads


def capacitated_kmeans(
    point_ids: Sequence[str],
    points_xy: Mapping[str, tuple[float, float]],
    demand: Mapping[str, int],
    k: int,
    capacity: int,
    seed: int = 1,
    n_init: int = 10,
    max_iter: int = 100,
    score_fn: Callable[[Assignment], tuple] | None = None,
) -> Assignment:
    """Capacity-aware K-Means++ with multi-start and overflow repair."""

    ids = list(point_ids)
    coords = np.asarray([points_xy[p] for p in ids], dtype=float)
    demand_arr = np.asarray([demand[p] for p in ids], dtype=int)
    best: tuple[tuple, Assignment] | None = None
    for restart in range(max(1, n_init)):
        rng = random.Random(seed + restart)
        centers = _init_kmeanspp(coords, k, rng, demand_arr.astype(float))
        labels = np.full(len(ids), -1, dtype=int)
        for _ in range(max_iter):
            new_labels, _ = _capacity_aware_assignment(
                coords, centers, demand_arr, capacity
            )
            centers = _update_centers(coords, new_labels, k, demand_arr.astype(float))
            if np.array_equal(new_labels, labels):
                labels = new_labels
                break
            labels = new_labels
        labels, _ = _capacity_aware_assignment(coords, centers, demand_arr, capacity)
        labels, loads = _repair_capacity(coords, labels, demand_arr, capacity, k)
        label_map = {pid: int(labels[i]) for i, pid in enumerate(ids)}
        assignment = Assignment(
            labels=label_map,
            loads=[int(x) for x in loads],
            k=k,
        )
        if score_fn is not None:
            key = score_fn(assignment)
        else:
            key = (float(assignment.overflow(capacity)), float(sum(loads**2)))
        if best is None or key < best[0]:
            best = (key, assignment)
    assert best is not None
    return best[1]
