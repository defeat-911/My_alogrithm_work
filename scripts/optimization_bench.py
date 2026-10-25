"""Measure two concrete optimizations used in the report.

1. Precomputed all-pairs distance matrix vs per-edge Dijkstra queries.
2. NumPy-vectorised K-Means assignment vs pure-Python nested loops.

Writes results/optimization.json.
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np

from campus_express.graph import RoadNetwork
from campus_express.io import load_campus

OUT = ROOT / "results" / "optimization.json"


def matrix_vs_dijkstra() -> dict[str, float]:
    campus = load_campus(ROOT / "data" / "campus.json")
    network = RoadNetwork(campus)
    rng = random.Random(2026)
    routes = [[rng.choice(campus.point_ids) for _ in range(20)] for _ in range(100)]
    keys = campus.key_node_ids
    index = {pid: i + 1 for i, pid in enumerate(campus.point_ids)}

    start = time.perf_counter()
    matrix = network.distance_matrix(keys)
    fast_total = 0.0
    for route in routes:
        prev = 0
        for pid in route:
            fast_total += float(matrix[prev, index[pid]])
            prev = index[pid]
        fast_total += float(matrix[prev, 0])
    fast_s = time.perf_counter() - start

    network = RoadNetwork(campus)  # fresh cache, no precomputation
    start = time.perf_counter()
    slow_total = 0.0
    for route in routes:
        network._cache.clear()
        prev = 0
        for pid in route:
            dist, _ = network.dijkstra(keys[prev], "length_m")
            slow_total += dist[keys[index[pid]]]
            prev = index[pid]
        dist, _ = network.dijkstra(keys[prev], "length_m")
        slow_total += dist[keys[0]]
    slow_s = time.perf_counter() - start
    return {
        "MATRIX_FAST_S": fast_s,
        "MATRIX_SLOW_S": slow_s,
        "MATRIX_SPEEDUP": slow_s / max(fast_s, 1e-9),
        "MATRIX_TOTAL_M": fast_total,
        "MATRIX_TOTAL_M_SLOW": slow_total,
    }


def kmeans_numpy_vs_python() -> dict[str, float]:
    rng = np.random.default_rng(2026)
    coords = rng.uniform(0, 1000, size=(30, 2))
    centers = rng.uniform(0, 1000, size=(10, 2))
    iterations = 200

    def py_assign():
        labels = []
        for x, y in coords:
            best = 0
            best_d = math.inf
            for k, (cx, cy) in enumerate(centers):
                d = (x - cx) ** 2 + (y - cy) ** 2
                if d < best_d:
                    best_d = d
                    best = k
            labels.append(best)
        return labels

    def np_assign():
        d2 = ((coords[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        return np.argmin(d2, axis=1)

    start = time.perf_counter()
    for _ in range(iterations):
        py_assign()
    py_s = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(iterations):
        np_assign()
    np_s = time.perf_counter() - start
    return {
        "KMEANS_SLOW_S": py_s,
        "KMEANS_FAST_S": np_s,
        "KMEANS_SPEEDUP": py_s / max(np_s, 1e-9),
    }


def main() -> None:
    result = {}
    result.update(matrix_vs_dijkstra())
    result.update(kmeans_numpy_vs_python())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
