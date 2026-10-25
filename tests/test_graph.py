from __future__ import annotations

import math

import networkx as nx
import numpy as np

from campus_express.graph import RoadNetwork
from campus_express.models import Campus


def _to_networkx(campus: Campus) -> nx.Graph:
    graph = nx.Graph()
    for node in campus.nodes:
        graph.add_node(node)
    for edge in campus.edges:
        graph.add_edge(edge.u, edge.v, weight=edge.length_m)
    for point_id, (node_id, length_m, _speed) in campus.point_links.items():
        graph.add_edge(point_id, node_id, weight=length_m)
    graph.add_edge(campus.center.id, campus.center.node_id, weight=0.0)
    return graph


def test_dijkstra_matches_networkx(campus):
    network = RoadNetwork(campus)
    graph = _to_networkx(campus)
    for source in campus.key_node_ids:
        expected = nx.single_source_dijkstra_path_length(graph, source, weight="weight")
        actual, _ = network.dijkstra(source, weight="length_m")
        for target in campus.key_node_ids:
            assert math.isclose(actual[target], expected[target], rel_tol=1e-9, abs_tol=1e-6)


def test_distance_matrix_symmetric_and_zero_diagonal(campus):
    network = RoadNetwork(campus)
    matrix = network.distance_matrix(campus.key_node_ids)
    assert matrix.shape == (31, 31)
    assert np.allclose(matrix, matrix.T)
    assert np.allclose(np.diag(matrix), 0.0)
    assert np.isfinite(matrix).all()


def test_shortest_path_length_matches_distance(campus):
    network = RoadNetwork(campus)
    path = network.shortest_path("D0", "D01")
    total = 0.0
    for u, v in zip(path, path[1:]):
        edge = next(
            (length for neighbor, length, _time in network.adj[u] if neighbor == v),
            None,
        )
        assert edge is not None
        total += edge
    assert math.isclose(total, network.dijkstra("D0")[0]["D01"], rel_tol=1e-9)


def test_connectivity(campus):
    network = RoadNetwork(campus)
    assert network.connected()
    assert network.unreachable_points() == []


def test_unreachable_point_detection(campus):
    broken_links = dict(campus.point_links)
    broken_links.pop("D01")
    broken = Campus(
        name=campus.name,
        bounds=campus.bounds,
        center=campus.center,
        points=campus.points,
        chutes=campus.chutes,
        nodes=campus.nodes,
        edges=campus.edges,
        point_links=broken_links,
    )
    network = RoadNetwork(broken)
    assert not network.connected()
    assert "D01" in network.unreachable_points()
