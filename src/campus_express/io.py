"""JSON/YAML loading and saving with light validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import (
    Campus,
    Chute,
    Package,
    Point,
    Priority,
    RoadEdge,
    TimeWindow,
    format_hhmm,
    parse_hhmm,
)


def load_config(path: str | Path = "config/default.yaml") -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_campus(path: str | Path = "data/campus.json") -> Campus:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    center_raw = raw["center"]
    center = Point(
        id=center_raw.get("id", "D0"),
        name=center_raw["name"],
        x_m=float(center_raw["x"]),
        y_m=float(center_raw["y"]),
        kind="depot",
        node_id=center_raw["node_id"],
    )

    points: dict[str, Point] = {}
    for item in raw["points"]:
        p = Point(
            id=item["id"],
            name=item["name"],
            x_m=float(item["x"]),
            y_m=float(item["y"]),
            kind=item.get("kind", "other"),
            node_id=item["node_id"],
        )
        if p.id in points:
            raise ValueError(f"duplicate point id: {p.id}")
        points[p.id] = p

    chutes: dict[str, Chute] = {}
    for item in raw.get("chutes", []):
        c = Chute(
            id=item["id"],
            name=item["name"],
            capacity_packages=int(item["capacity_packages"]),
            capacity_kg=float(item.get("capacity_kg", 1e9)),
        )
        chutes[c.id] = c

    nodes = {item["id"]: (float(item["x"]), float(item["y"])) for item in raw["nodes"]}
    edges = [
        RoadEdge(
            u=item["u"],
            v=item["v"],
            length_m=float(item["length_m"]),
            speed_mps=float(item.get("speed_mps", 4.0)),
        )
        for item in raw["edges"]
    ]
    point_links = {
        item["point_id"]: (
            item["node_id"],
            float(item["length_m"]),
            float(item.get("speed_mps", 1.2)),
        )
        for item in raw.get("point_links", [])
    }

    return Campus(
        name=raw.get("meta", {}).get("name", "campus"),
        bounds={
            "width_m": float(raw.get("bounds", {}).get("width_m", 1200)),
            "height_m": float(raw.get("bounds", {}).get("height_m", 1000)),
        },
        center=center,
        points=points,
        chutes=chutes,
        nodes=nodes,
        edges=edges,
        point_links=point_links,
    )


def load_packages(path: str | Path) -> list[Package]:
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    packages: list[Package] = []
    for item in raw["packages"]:
        window_raw = item["window"]
        if isinstance(window_raw, dict):
            start, end = window_raw["start"], window_raw["end"]
        else:
            start, end = window_raw
        pkg = Package(
            id=item["id"],
            dest_id=item["dest_id"],
            weight_kg=float(item["weight_kg"]),
            priority=Priority.from_value(item["priority"]),
            window=TimeWindow(parse_hhmm(start), parse_hhmm(end)),
            bucket=int(item.get("bucket", 0)),
        )
        packages.append(pkg)
    return packages


def save_packages(
    packages: list[Package],
    path: str | Path,
    meta: dict[str, Any] | None = None,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": meta or {},
        "packages": [
            {
                "id": p.id,
                "dest_id": p.dest_id,
                "weight_kg": round(p.weight_kg, 3),
                "priority": int(p.priority),
                "window": {
                    "start": format_hhmm(p.window.start_min),
                    "end": format_hhmm(p.window.end_min),
                },
                "bucket": p.bucket,
            }
            for p in packages
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def validate_packages(packages: list[Package], campus: Campus) -> None:
    if not packages:
        raise ValueError("package list is empty")
    ids = set()
    for pkg in packages:
        if pkg.id in ids:
            raise ValueError(f"duplicate package id: {pkg.id}")
        ids.add(pkg.id)
        if pkg.dest_id not in campus.points:
            raise ValueError(f"unknown destination: {pkg.dest_id}")
        if pkg.weight_kg <= 0:
            raise ValueError(f"non-positive weight: {pkg.id}")
        if pkg.window.start_min < 0 or pkg.window.end_min > 24 * 60:
            raise ValueError(f"window outside day: {pkg.id}")
