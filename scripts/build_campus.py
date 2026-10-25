"""Build a deterministic simulated campus map.

Run from the project root:

    python scripts/build_campus.py

The output is ``data/campus.json``.  The map is a 9 x 9 grid of roads
(1200 m x 1000 m), 30 named delivery points, one sorting centre with 10
chutes, and short links from each point to its nearest road node.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "campus.json"

XS = [0, 150, 300, 450, 600, 750, 900, 1050, 1200]
YS = [0, 125, 250, 375, 500, 625, 750, 875, 1000]
NX, NY = len(XS), len(YS)


def node_id(ix: int, iy: int) -> str:
    return f"N{iy * NX + ix:03d}"


POINTS = [
    ("D01", "松园1号宿舍楼", 75, 75, "dorm"),
    ("D02", "松园2号宿舍楼", 225, 75, "dorm"),
    ("D03", "松园3号宿舍楼", 375, 75, "dorm"),
    ("D04", "松园4号宿舍楼", 525, 75, "dorm"),
    ("D05", "松园5号宿舍楼", 675, 75, "dorm"),
    ("D06", "松园6号宿舍楼", 825, 75, "dorm"),
    ("D07", "松园7号宿舍楼", 975, 75, "dorm"),
    ("D08", "松园8号宿舍楼", 1125, 75, "dorm"),
    ("D09", "松园9号宿舍楼", 75, 925, "dorm"),
    ("D10", "松园10号宿舍楼", 225, 925, "dorm"),
    ("D11", "松园11号宿舍楼", 375, 925, "dorm"),
    ("D12", "松园12号宿舍楼", 525, 925, "dorm"),
    ("T01", "梅园1号教学楼", 825, 925, "teaching"),
    ("T02", "梅园2号教学楼", 975, 925, "teaching"),
    ("T03", "梅园3号教学楼", 1125, 925, "teaching"),
    ("T04", "梅园4号教学楼", 75, 300, "teaching"),
    ("T05", "梅园5号教学楼", 1125, 300, "teaching"),
    ("T06", "梅园6号教学楼", 75, 700, "teaching"),
    ("T07", "梅园7号教学楼", 1125, 700, "teaching"),
    ("T08", "梅园8号教学楼", 600, 800, "teaching"),
    ("L01", "图书馆", 300, 300, "library"),
    ("C01", "学士餐厅", 300, 700, "canteen"),
    ("C02", "学海餐厅", 900, 300, "canteen"),
    ("C03", "学子食堂", 900, 700, "canteen"),
    ("G01", "体育馆", 600, 150, "gym"),
    ("A01", "行政楼", 600, 850, "admin"),
    ("E01", "综合实验楼", 450, 300, "lab"),
    ("E02", "理化综合楼", 750, 700, "lab"),
    ("H01", "校医院", 150, 500, "hospital"),
    ("I01", "创新创业中心", 1050, 500, "innovation"),
]


def build() -> dict:
    nodes = [
        {"id": node_id(ix, iy), "x": float(x), "y": float(y)}
        for iy, y in enumerate(YS)
        for ix, x in enumerate(XS)
    ]

    edges = []
    seen = set()

    def add_edge(a: dict, b: dict) -> None:
        key = tuple(sorted((a["id"], b["id"])))
        if key in seen:
            return
        seen.add(key)
        length = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
        edges.append(
            {
                "u": a["id"],
                "v": b["id"],
                "length_m": round(length, 2),
                "speed_mps": 4.0,
            }
        )

    for iy in range(NY):
        for ix in range(NX):
            here = nodes[iy * NX + ix]
            if ix + 1 < NX:
                add_edge(here, nodes[iy * NX + ix + 1])
            if iy + 1 < NY:
                add_edge(here, nodes[(iy + 1) * NX + ix])

    # A few diagonal pedestrian paths, to avoid a purely Manhattan graph.
    for ix, iy in [(0, 0), (2, 0), (4, 0), (6, 0), (2, 4), (6, 4), (0, 7), (8, 7)]:
        if ix + 1 < NX and iy + 1 < NY:
            add_edge(nodes[iy * NX + ix], nodes[(iy + 1) * NX + ix + 1])

    point_items = []
    point_links = []
    for pid, name, x, y, kind in POINTS:
        nearest = min(
            nodes,
            key=lambda n: (n["x"] - x) ** 2 + (n["y"] - y) ** 2,
        )
        link_len = math.hypot(nearest["x"] - x, nearest["y"] - y)
        point_items.append(
            {
                "id": pid,
                "name": name,
                "x": float(x),
                "y": float(y),
                "kind": kind,
                "node_id": nearest["id"],
            }
        )
        point_links.append(
            {
                "point_id": pid,
                "node_id": nearest["id"],
                "length_m": round(link_len, 2),
                "speed_mps": 1.2,
            }
        )

    chutes = [
        {
            "id": f"C{i:02d}",
            "name": f"{i}号格口",
            "capacity_packages": 60,
            "capacity_kg": 40.0,
        }
        for i in range(1, 11)
    ]

    return {
        "meta": {
            "name": "河南理工大学校园",
            "version": 1,
            "length_unit": "m",
            "time_unit": "min",
            "note": "Course-design simulation, not a real campus map.",
        },
        "bounds": {"width_m": 1200.0, "height_m": 1000.0},
        "center": {
            "id": "D0",
            "name": "校园快递分拣中心",
            "x": 600.0,
            "y": 500.0,
            "node_id": node_id(4, 4),
        },
        "points": point_items,
        "chutes": chutes,
        "nodes": nodes,
        "edges": edges,
        "point_links": point_links,
    }


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = build()
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(f"wrote {OUT}")
    print(
        f"points={len(payload['points'])} nodes={len(payload['nodes'])} "
        f"edges={len(payload['edges'])} chutes={len(payload['chutes'])}"
    )


if __name__ == "__main__":
    main()
