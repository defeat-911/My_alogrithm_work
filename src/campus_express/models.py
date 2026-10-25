"""Core data models for the campus express problem.

The models deliberately keep the graph representation simple so that the
algorithms (Dijkstra, K-Means, savings, ALNS) can be implemented from scratch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable


class Priority(IntEnum):
    """Package priority. Higher value means more urgent."""

    NORMAL = 1
    URGENT = 2
    EXPRESS = 3

    @classmethod
    def from_value(cls, value: int | str) -> "Priority":
        if isinstance(value, str):
            mapping = {"normal": 1, "urgent": 2, "express": 3}
            return cls(mapping[value.strip().lower()])
        return cls(int(value))


def parse_hhmm(text: str) -> int:
    """Parse ``HH:MM`` into minutes after midnight."""

    hour, minute = text.strip().split(":")
    h, m = int(hour), int(minute)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"invalid time: {text!r}")
    return h * 60 + m


def format_hhmm(minutes: float) -> str:
    """Format minutes after midnight as ``HH:MM``."""

    total = int(round(minutes))
    return f"{total // 60:02d}:{total % 60:02d}"


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start_min: int
    end_min: int

    def __post_init__(self) -> None:
        if not (0 <= self.start_min < self.end_min <= 24 * 60):
            raise ValueError(
                f"invalid time window: {self.start_min}..{self.end_min}"
            )

    @property
    def duration(self) -> int:
        return self.end_min - self.start_min

    def contains(self, t: float) -> bool:
        return self.start_min <= t <= self.end_min

    def overlaps(self, other: "TimeWindow") -> bool:
        return max(self.start_min, other.start_min) < min(
            self.end_min, other.end_min
        )

    def __str__(self) -> str:
        return f"{format_hhmm(self.start_min)}-{format_hhmm(self.end_min)}"


@dataclass(frozen=True, slots=True)
class Point:
    id: str
    name: str
    x_m: float
    y_m: float
    kind: str
    node_id: str


@dataclass(frozen=True, slots=True)
class Chute:
    id: str
    name: str
    capacity_packages: int
    capacity_kg: float


@dataclass(frozen=True, slots=True)
class Package:
    id: str
    dest_id: str
    weight_kg: float
    priority: Priority
    window: TimeWindow
    bucket: int


@dataclass(frozen=True, slots=True)
class Task:
    """A delivery task: one stop at a point within one time-window bucket.

    Packages at the same point and bucket are aggregated.  ``priority_score``
    is the package-count-weighted priority (1.0--3.0), which preserves urgency
    better than a plain ``max`` while keeping the task count manageable.
    """

    id: str
    point_id: str
    window: TimeWindow
    package_ids: tuple[str, ...]
    demand: int
    weight_kg: float
    priority: Priority
    priority_score: float
    service_s: float

    @property
    def point_key(self) -> str:
        return self.point_id


@dataclass(frozen=True, slots=True)
class Courier:
    id: int
    capacity_packages: int
    capacity_kg: float
    speed_mps: float
    shift_start: int
    shift_end: int


@dataclass
class Route:
    courier_id: int
    task_ids: list[str] = field(default_factory=list)


@dataclass
class Solution:
    routes: list[Route] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)

    def all_task_ids(self) -> list[str]:
        return [tid for route in self.routes for tid in route.task_ids]

    def copy(self) -> "Solution":
        return Solution(
            routes=[Route(r.courier_id, list(r.task_ids)) for r in self.routes],
            unassigned=list(self.unassigned),
            metrics=dict(self.metrics),
        )


@dataclass(frozen=True, slots=True)
class RoadEdge:
    u: str
    v: str
    length_m: float
    speed_mps: float


@dataclass
class Campus:
    name: str
    bounds: dict[str, float]
    center: Point
    points: dict[str, Point]
    chutes: dict[str, Chute]
    nodes: dict[str, tuple[float, float]]
    edges: list[RoadEdge]
    point_links: dict[str, tuple[str, float, float]]

    @property
    def point_ids(self) -> list[str]:
        return sorted(self.points)

    @property
    def node_ids(self) -> list[str]:
        return sorted(self.nodes)

    @property
    def key_node_ids(self) -> list[str]:
        """Center plus delivery points, used for the routing matrices."""

        return [self.center.id] + self.point_ids

    def point_xy(self, point_id: str) -> tuple[float, float]:
        if point_id == self.center.id:
            return self.center.x_m, self.center.y_m
        p = self.points[point_id]
        return p.x_m, p.y_m

    def demand_by_point(self, packages: Iterable[Package]) -> dict[str, int]:
        demand = {pid: 0 for pid in self.points}
        for pkg in packages:
            demand[pkg.dest_id] += 1
        return demand
