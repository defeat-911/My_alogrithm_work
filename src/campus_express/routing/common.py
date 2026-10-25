"""Scheduling, route evaluation and the routing context."""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Mapping, Sequence

import numpy as np

from ..models import Courier, Route, Solution, Task


@dataclass
class Schedule:
    task_ids: list[str]
    arrivals: dict[str, float]
    waits: dict[str, float]
    departures: dict[str, float]
    distance_m: float
    travel_min: float
    waiting_min: float
    tardiness_min: float
    end_time: float
    load: int
    weight_kg: float
    feasible: bool
    reasons: list[str] = field(default_factory=list)
    priority_weighted_arrival: float = 0.0


@dataclass
class RoutingContext:
    tasks: dict[str, Task]
    task_order: list[str]
    point_index: Mapping[str, int]
    dist: np.ndarray
    couriers: list[Courier]
    shift_start: int
    shift_end: int
    hard_windows: bool = True
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "distance": 0.45,
            "makespan": 0.25,
            "priority": 0.20,
            "balance": 0.10,
        }
    )
    tardiness_weight: float = 10.0
    infeasible_penalty: float = 1e6

    def __post_init__(self) -> None:
        self.task_ids = list(self.task_order)
        self.courier_by_id = {c.id: c for c in self.couriers}

    # ------------------------------------------------------------------ helpers
    def task_node(self, task_id: str) -> int:
        return int(self.point_index[self.tasks[task_id].point_id])

    def route_distance(self, task_ids: Sequence[str]) -> float:
        if not task_ids:
            return 0.0
        total = 0.0
        current = 0
        for tid in task_ids:
            node = self.task_node(tid)
            total += float(self.dist[current, node])
            current = node
        total += float(self.dist[current, 0])
        return total

    def route_load(self, task_ids: Sequence[str]) -> tuple[int, float]:
        demand = sum(self.tasks[t].demand for t in task_ids)
        weight = sum(self.tasks[t].weight_kg for t in task_ids)
        return demand, weight

    def schedule_route(
        self, courier_id: int, task_ids: Sequence[str]
    ) -> Schedule:
        courier = self.courier_by_id[courier_id]
        arrivals: dict[str, float] = {}
        waits: dict[str, float] = {}
        departures: dict[str, float] = {}
        reasons: list[str] = []
        current_time = float(self.shift_start)
        current_node = 0
        distance = 0.0
        waiting = 0.0
        tardiness = 0.0
        load = 0
        weight = 0.0
        priority_sum = 0.0
        priority_arrival_sum = 0.0

        for tid in task_ids:
            task = self.tasks[tid]
            node = self.task_node(tid)
            travel_m = float(self.dist[current_node, node])
            if not np.isfinite(travel_m):
                return Schedule(
                    task_ids=list(task_ids),
                    arrivals={},
                    waits={},
                    departures={},
                    distance_m=float("inf"),
                    travel_min=float("inf"),
                    waiting_min=0.0,
                    tardiness_min=float("inf"),
                    end_time=float("inf"),
                    load=load,
                    weight_kg=weight,
                    feasible=False,
                    reasons=["unreachable task"],
                )
            distance += travel_m
            current_time += travel_m / courier.speed_mps / 60.0
            if current_time < task.window.start_min:
                wait = task.window.start_min - current_time
                waiting += wait
                current_time = task.window.start_min
            else:
                wait = 0.0
            if current_time > task.window.end_min:
                late = current_time - task.window.end_min
                tardiness += late
                if self.hard_windows:
                    reasons.append(f"late:{tid}")
            arrivals[tid] = current_time
            waits[tid] = wait
            service_min = task.service_s / 60.0
            current_time += service_min
            departures[tid] = current_time
            load += task.demand
            weight += task.weight_kg
            priority_sum += task.priority_score
            priority_arrival_sum += task.priority_score * arrivals[tid]
            current_node = node

        # Return to the depot.
        travel_back = float(self.dist[current_node, 0])
        distance += travel_back
        current_time += travel_back / courier.speed_mps / 60.0

        if load > courier.capacity_packages:
            reasons.append("capacity_packages")
        if weight > courier.capacity_kg + 1e-9:
            reasons.append("capacity_kg")
        if current_time > self.shift_end + 1e-9:
            reasons.append("shift_end")
        feasible = not reasons
        return Schedule(
            task_ids=list(task_ids),
            arrivals=arrivals,
            waits=waits,
            departures=departures,
            distance_m=distance,
            travel_min=distance / courier.speed_mps / 60.0,
            waiting_min=waiting,
            tardiness_min=tardiness,
            end_time=current_time,
            load=load,
            weight_kg=weight,
            feasible=feasible,
            reasons=reasons,
            priority_weighted_arrival=(
                priority_arrival_sum / priority_sum if priority_sum else 0.0
            ),
        )

    def empty_solution(self) -> Solution:
        return Solution(routes=[Route(c.id, []) for c in self.couriers])

    def solution_from_routes(self, routes: Sequence[Sequence[str]]) -> Solution:
        return Solution(
            routes=[
                Route(self.couriers[i].id, list(route))
                for i, route in enumerate(routes)
                if i < len(self.couriers)
            ]
        )

    def all_task_ids(self) -> list[str]:
        return list(self.task_order)

    def evaluate(self, solution: Solution) -> Solution:
        served: list[str] = []
        total_distance = 0.0
        makespan = 0.0
        waiting = 0.0
        tardiness = 0.0
        late_tasks = 0
        priority_arrivals: list[tuple[float, float]] = []
        loads: list[int] = []
        feasible = True
        reasons: list[str] = []

        for route in solution.routes:
            if route.courier_id not in self.courier_by_id:
                feasible = False
                reasons.append("unknown courier")
                continue
            schedule = self.schedule_route(route.courier_id, route.task_ids)
            served.extend(route.task_ids)
            total_distance += schedule.distance_m
            makespan = max(makespan, schedule.end_time)
            waiting += schedule.waiting_min
            tardiness += schedule.tardiness_min
            late_tasks += sum(
                1
                for tid in route.task_ids
                if schedule.arrivals.get(tid, 0.0)
                > self.tasks[tid].window.end_min
            )
            loads.append(schedule.load)
            for tid in route.task_ids:
                if tid in schedule.arrivals:
                    priority_arrivals.append(
                        (
                            self.tasks[tid].priority_score,
                            schedule.arrivals[tid],
                        )
                    )
            if not schedule.feasible:
                feasible = False
                reasons.extend(schedule.reasons)

        expected = set(self.task_order)
        served_set = set(served)
        unassigned = sorted(expected - served_set)
        duplicates = len(served) - len(served_set)
        if unassigned:
            feasible = False
            reasons.append(f"unassigned:{len(unassigned)}")
        if duplicates:
            feasible = False
            reasons.append(f"duplicates:{duplicates}")
        if len(solution.routes) > len(self.couriers):
            feasible = False
            reasons.append("too_many_routes")

        while len(loads) < len(self.couriers):
            loads.append(0)
        load_cv = 0.0
        if loads and mean(loads) > 0:
            load_cv = pstdev(loads) / mean(loads)
        priority_arrival = (
            sum(w * a for w, a in priority_arrivals)
            / sum(w for w, _ in priority_arrivals)
            if priority_arrivals
            else 0.0
        )
        on_time_rate = (
            1.0 - late_tasks / len(expected) if expected else 1.0
        )
        objective = (
            self.weights["distance"] * total_distance / 1000.0
            + self.weights["makespan"] * makespan / 60.0
            + self.weights["priority"] * priority_arrival / 60.0
            + self.weights["balance"] * load_cv
            + self.tardiness_weight * tardiness / 60.0
        )
        if not feasible:
            objective += self.infeasible_penalty
        solution.unassigned = unassigned
        solution.metrics = {
            "feasible": 1.0 if feasible else 0.0,
            "distance_m": total_distance,
            "distance_km": total_distance / 1000.0,
            "makespan_min": makespan,
            "waiting_min": waiting,
            "tardiness_min": tardiness,
            "on_time_rate": on_time_rate,
            "priority_weighted_arrival": priority_arrival,
            "load_cv": load_cv,
            "n_routes": float(len(solution.routes)),
            "n_tasks": float(len(expected)),
            "unassigned": float(len(unassigned)),
            "objective": objective,
            "reasons": ";".join(sorted(set(reasons))),
        }
        return solution


def route_distance(task_ids: Sequence[str], ctx: RoutingContext) -> float:
    return ctx.route_distance(task_ids)
