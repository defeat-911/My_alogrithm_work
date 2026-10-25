"""Campus road network and Dijkstra shortest paths."""

from __future__ import annotations

import heapq
import math
from collections import defaultdict
from typing import Iterable, Sequence

import numpy as np

from .models import Campus


class RoadNetwork:
    """Weighted undirected graph for the campus.

    Nodes include road intersections, the depot and all delivery points.
    Delivery points are connected to the nearest road node by a short link.
    """

    def __init__(self, campus: Campus) -> None:
        self.campus = campus
        self.adj: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
        for edge in campus.edges:
            time_s = edge.length_m / edge.speed_mps
            self.adj[edge.u].append((edge.v, edge.length_m, time_s))
            self.adj[edge.v].append((edge.u, edge.length_m, time_s))
        for point_id, (node_id, length_m, speed_mps) in campus.point_links.items():
            time_s = length_m / speed_mps
            self.adj[point_id].append((node_id, length_m, time_s))
            self.adj[node_id].append((point_id, length_m, time_s))
        # The depot is represented by its own key id and by a road node.
        depot_id = campus.center.id
        depot_node = campus.center.node_id
        self.adj[depot_id].append((depot_node, 0.0, 0.0))
        self.adj[depot_node].append((depot_id, 0.0, 0.0))
        self._cache: dict[tuple[str, str], tuple[dict[str, float], dict[str, str]]] = {}

    # ------------------------------------------------------------------ Dijkstra
    def dijkstra(
        self, source: str, weight: str = "length_m"
    ) -> tuple[dict[str, float], dict[str, str]]:
        """Return distances and predecessors from ``source``.

        ``weight`` is either ``"length_m"`` or ``"time_s"``.
        """

        if weight not in {"length_m", "time_s"}:
            raise ValueError(f"unknown weight: {weight}")
        cache_key = (source, weight)
        if cache_key in self._cache:
            return self._cache[cache_key]

        if source not in self.adj:
            raise KeyError(f"unknown graph node: {source}")

        dist: dict[str, float] = {source: 0.0}
        prev: dict[str, str] = {}
        heap: list[tuple[float, str]] = [(0.0, source)]
        while heap:
            d, u = heapq.heappop(heap)
            if d > dist.get(u, math.inf):
                continue
            for v, length_m, time_s in self.adj[u]:
                step = length_m if weight == "length_m" else time_s
                nd = d + step
                if nd < dist.get(v, math.inf):
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))
        self._cache[cache_key] = (dist, prev)
        return dist, prev

    def shortest_path(
        self, source: str, target: str, weight: str = "length_m"
    ) -> list[str]:
        dist, prev = self.dijkstra(source, weight=weight)
        if target not in dist:
            raise ValueError(f"no path from {source} to {target}")
        path = [target]
        while path[-1] != source:
            path.append(prev[path[-1]])
        path.reverse()
        return path

    # ------------------------------------------------------------------ matrices
    def distance_matrix(self, node_ids: Sequence[str]) -> np.ndarray:
        ids = list(node_ids)
        mat = np.full((len(ids), len(ids)), np.inf, dtype=float)
        for i, src in enumerate(ids):
            dist, _ = self.dijkstra(src, weight="length_m")
            for j, dst in enumerate(ids):
                mat[i, j] = dist.get(dst, math.inf)
        return mat

    def time_matrix(self, node_ids: Sequence[str], speed_mps: float) -> np.ndarray:
        return self.distance_matrix(node_ids) / float(speed_mps)

    def key_distance_matrix(self) -> np.ndarray:
        return self.distance_matrix(self.campus.key_node_ids)

    def key_time_matrix(self, speed_mps: float) -> np.ndarray:
        return self.time_matrix(self.campus.key_node_ids, speed_mps)

    # ------------------------------------------------------------------ helpers
    def connected(self, source: str | None = None) -> bool:
        src = source or self.campus.center.id
        dist, _ = self.dijkstra(src, weight="length_m")
        return all(pid in dist for pid in self.campus.point_ids)

    def unreachable_points(self) -> list[str]:
        dist, _ = self.dijkstra(self.campus.center.id, weight="length_m")
        return [pid for pid in self.campus.point_ids if pid not in dist]

    def nearest_road_node(self, x_m: float, y_m: float) -> str:
        return min(
            self.campus.nodes,
            key=lambda nid: (self.campus.nodes[nid][0] - x_m) ** 2
            + (self.campus.nodes[nid][1] - y_m) ** 2,
        )

    def matrix_index(self, node_ids: Iterable[str]) -> dict[str, int]:
        return {nid: i for i, nid in enumerate(node_ids)}
