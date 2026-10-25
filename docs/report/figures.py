"""Generate the v1 report figures from the saved experiment results.

Run after the benchmark:

    python docs/report/figures.py
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle
from PIL import Image, ImageDraw, ImageFont

from campus_express.data_gen import generate_packages
from campus_express.io import load_campus, load_config
from campus_express.models import Priority, format_hhmm
from campus_express.routing.alns import ALNSParams, alns
from campus_express.solver import (
    build_context_from_data,
    solve_routing,
    solve_sorting,
)

OUT = ROOT / "docs" / "report" / "figures"
RESULTS = ROOT / "results"
OUT.mkdir(parents=True, exist_ok=True)

NAVY = "#2F4B6E"
RED = "#B4553F"
GREY = "#8A8F98"
LIGHT = "#D9E2EC"
SAND = "#C9A227"
GREEN = "#4E7A5B"
PURPLE = "#7B6D8D"
CLUSTER_COLORS = [
    "#2F4B6E", "#B4553F", "#4E7A5B", "#C9A227", "#7B6D8D",
    "#5B8FA8", "#A6634A", "#6A8D73", "#B08B4F", "#8A8F98",
]


def _chinese():
    plt.rcParams["font.family"] = "SimSun"
    plt.rcParams["axes.unicode_minus"] = False


def _english():
    plt.rcParams["font.family"] = "Times New Roman"
    plt.rcParams["axes.unicode_minus"] = False


def _save(fig, name: str, tight: bool = True) -> None:
    path = OUT / name
    kwargs = {"dpi": 300, "facecolor": "white"}
    if tight:
        kwargs["bbox_inches"] = "tight"
    fig.savefig(path, **kwargs)
    plt.close(fig)
    print("wrote", path)


def _tidy(ax, grid_axis="y"):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#BBBBBB")
    ax.tick_params(colors="#444444", length=3)
    if grid_axis:
        ax.grid(axis=grid_axis, color="#E8E8E8", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)


def _box(ax, x, y, w, h, text, fc=LIGHT, ec=NAVY, fontsize=9, textcolor="#222222"):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.0, edgecolor=ec, facecolor=fc, zorder=2,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, color=textcolor, zorder=3)


def _arrow(ax, x1, y1, x2, y2, color=GREY):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=10,
        linewidth=1.0, color=color, zorder=1,
    ))


# --------------------------------------------------------------------------- data
def _data():
    campus = load_campus(ROOT / "data" / "campus.json")
    config = load_config(ROOT / "config" / "default.yaml")
    packages = generate_packages(campus, 500, 1, config)
    ctx = build_context_from_data(campus, config, packages)
    return campus, config, ctx


def _summary() -> dict:
    path = RESULTS / "summary.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh).get("summary", {})


def _metric(summary, exp, scale, method, metric, default=0.0):
    try:
        return summary[exp][str(scale)][method][metric]["mean"]
    except KeyError:
        return default


# --------------------------------------------------------------------------- figures
def fig_campus(campus):
    _chinese()
    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    for edge in campus.edges:
        x1, y1 = campus.nodes[edge.u]
        x2, y2 = campus.nodes[edge.v]
        ax.plot([x1, x2], [y1, y2], color="#D5D9DE", linewidth=0.7, zorder=1)
    for pid, (node_id, _length, _speed) in campus.point_links.items():
        x1, y1 = campus.point_xy(pid)
        x2, y2 = campus.nodes[node_id]
        ax.plot([x1, x2], [y1, y2], color="#E3E6E9", linewidth=0.5, zorder=1)

    kind_color = {
        "dorm": NAVY, "teaching": RED, "library": GREEN, "canteen": SAND,
        "gym": PURPLE, "admin": GREY, "lab": "#5B8FA8", "hospital": "#A6634A",
        "innovation": "#6A8D73",
    }
    for pid, point in campus.points.items():
        ax.scatter(point.x_m, point.y_m, s=38, color=kind_color.get(point.kind, GREY),
                   edgecolor="white", linewidth=0.7, zorder=3)
        ax.text(point.x_m + 12, point.y_m + 10, pid, fontsize=6.2, color="#333333", zorder=4)
    ax.scatter(campus.center.x_m, campus.center.y_m, marker="*", s=240,
               color=RED, edgecolor="white", linewidth=1.0, zorder=5)
    ax.text(campus.center.x_m + 20, campus.center.y_m - 30, "分拣中心", fontsize=9,
            color=RED, zorder=6)
    ax.set_xlim(-30, campus.bounds["width_m"] + 30)
    ax.set_ylim(-30, campus.bounds["height_m"] + 30)
    ax.set_aspect("equal")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title("模拟校园路网、30 个配送点与分拣中心", fontsize=11)
    handles = [
        plt.Line2D([], [], marker="o", linestyle="", color=c, label=k)
        for k, c in [("宿舍", NAVY), ("教学", RED), ("食堂", SAND), ("其他", GREY)]
    ]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=8, ncol=2)
    _tidy(ax, grid_axis=None)
    _save(fig, "fig1_campus.png")


def fig_architecture():
    _chinese()
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")
    _box(ax, 0.4, 5.7, 9.2, 0.8, "输入层：校园地图 / 包裹数据 / 配置（JSON + YAML）", fc="#EEF2F6")
    _box(ax, 0.4, 4.6, 4.3, 0.75, "路网层\nDijkstra + 全源最短路矩阵", fc="#E3ECF4")
    _box(ax, 5.3, 4.6, 4.3, 0.75, "任务层\n(配送点, 时间窗) 聚合", fc="#E3ECF4")
    _box(ax, 0.4, 3.2, 4.3, 0.9, "分拣层\n网格/Sweep/K-Means++/容量 K-Means+LS", fc="#F4E9E4", fontsize=8)
    _box(ax, 5.3, 3.2, 4.3, 0.9, "路径层\nNN+EDD/Savings/2-opt/ALNS", fc="#F4E9E4", fontsize=8)
    _box(ax, 0.4, 1.9, 9.2, 0.7, "评估层：距离 / 完工 / 准时率 / 优先级 / 负载均衡 / 可行性校验", fc="#E8F0E8")
    _box(ax, 0.4, 0.6, 9.2, 0.7, "输出层：JSON 结果 / 指标 CSV / 图表 / 报告", fc="#F3F1E6")
    _arrow(ax, 5, 5.7, 5, 5.35)
    _arrow(ax, 2.55, 4.6, 2.55, 4.1)
    _arrow(ax, 7.45, 4.6, 7.45, 4.1)
    _arrow(ax, 2.55, 3.2, 2.55, 2.6)
    _arrow(ax, 7.45, 3.2, 7.45, 2.6)
    _arrow(ax, 5, 1.9, 5, 1.3)
    ax.text(5, 5.15, "数据校验 / 可行性预检", ha="center", fontsize=7, color=GREY)
    _save(fig, "fig1_architecture.png")


def fig_iteration():
    _chinese()
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.text(2.4, 7.6, "分拣：从粗糙分区到容量约束聚类", ha="center", fontsize=10, color=NAVY)
    ax.text(7.4, 7.6, "路径：从短视构造到 ALNS", ha="center", fontsize=10, color=RED)
    left = [
        ("网格 / 行政分区", "负载不均、跨区路线长"),
        ("Sweep 扫描", "工作量均衡，区域狭长"),
        ("K-Means++", "空间紧凑，可能爆仓"),
        ("容量 K-Means + 局部搜索", "容量可行、CV 下降"),
    ]
    right = [
        ("最近邻 + EDD", "短视、路线交叉"),
        ("Clarke-Wright", "距离下降，窗口可行性差"),
        ("2-opt / Or-opt", "帧内优化，局部最优"),
        ("跨路径 + ALNS", "进一步下降，时间上升"),
    ]
    for i, (title, defect) in enumerate(left):
        y = 6.2 - i * 1.55
        _box(ax, 0.5, y, 3.7, 0.75, title, fc="#E3ECF4", fontsize=9)
        ax.text(0.55, y - 0.28, defect, fontsize=7.2, color=GREY)
        if i < len(left) - 1:
            _arrow(ax, 2.35, y, 2.35, y - 0.8, color=NAVY)
    for i, (title, defect) in enumerate(right):
        y = 6.2 - i * 1.55
        _box(ax, 5.5, y, 3.7, 0.75, title, fc="#F4E9E4", fontsize=9)
        ax.text(5.55, y - 0.28, defect, fontsize=7.2, color=GREY)
        if i < len(right) - 1:
            _arrow(ax, 7.35, y, 7.35, y - 0.8, color=RED)
    _save(fig, "fig2_iteration.png")


def fig_kmeans_capacity(campus, assignment):
    _chinese()
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.5), gridspec_kw={"width_ratios": [1.35, 1]})
    ax = axes[0]
    for pid, point in campus.points.items():
        c = CLUSTER_COLORS[assignment.labels[pid] % len(CLUSTER_COLORS)]
        ax.scatter(point.x_m, point.y_m, s=40, color=c, edgecolor="white", linewidth=0.6, zorder=2)
        ax.text(point.x_m + 12, point.y_m + 10, pid, fontsize=6, color="#333333")
    ax.scatter(campus.center.x_m, campus.center.y_m, marker="*", s=200, color=RED,
               edgecolor="white", zorder=4)
    ax.set_aspect("equal")
    ax.set_title("容量约束 K-Means 分区", fontsize=10)
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    _tidy(ax, grid_axis=None)

    ax = axes[1]
    colors = [CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(len(assignment.loads))]
    ax.bar(range(1, len(assignment.loads) + 1), assignment.loads, color=colors, zorder=2)
    ax.axhline(60, color=RED, linestyle="--", linewidth=1.1, label="格口容量 60")
    ax.set_xlabel("格口编号")
    ax.set_ylabel("包裹数")
    ax.set_title("各格口负载", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    _tidy(ax)
    fig.tight_layout()
    _save(fig, "fig2_kmeans_capacity.png")


def fig_savings():
    _chinese()
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2))
    pts = {
        "0": (0, 0), "1": (1.2, 2.4), "2": (2.6, 1.2),
        "3": (3.4, 3.0), "4": (4.8, 1.4), "5": (5.6, 2.8),
    }
    before = ["0", "1", "3", "2", "4", "5", "0"]
    after = ["0", "1", "2", "4", "3", "5", "0"]
    for ax, route, title in [(axes[0], before, "优化前：交叉路线"), (axes[1], after, "2-opt 后：交叉消除")]:
        for key, (x, y) in pts.items():
            ax.scatter(x, y, s=60, color=NAVY if key != "0" else RED,
                       marker="*" if key == "0" else "o",
                       edgecolor="white", zorder=3)
            ax.text(x + 0.08, y + 0.08, "中心" if key == "0" else key, fontsize=8)
        for a, b in zip(route, route[1:]):
            x1, y1 = pts[a]
            x2, y2 = pts[b]
            ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                        arrowprops=dict(arrowstyle="->", color=RED, linewidth=1.3))
        ax.set_title(title, fontsize=10)
        ax.set_xlim(-0.3, 6.2)
        ax.set_ylim(-0.5, 3.6)
        ax.set_aspect("equal")
        ax.axis("off")
    fig.tight_layout()
    _save(fig, "fig2_savings.png")


def fig_flow():
    _chinese()
    fig, ax = plt.subplots(figsize=(5.6, 6.8))
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 10)
    ax.axis("off")
    steps = [
        "读取配置、校园地图与包裹数据",
        "构建路网，Dijkstra 预计算最短路矩阵",
        "按 (配送点, 时间窗) 聚合任务",
        "分拣：网格 / Sweep / K-Means++ / 容量 K-Means+LS",
        "路径：NN+EDD / Savings / 2-opt / ALNS",
        "评估：距离、完工、准时率、优先级、均衡",
        "校验可行性并输出 JSON / 图表 / 报告",
    ]
    y = 8.8
    for i, text in enumerate(steps):
        _box(ax, 0.4, y, 5.2, 0.85, text, fc="#EEF2F6" if i % 2 == 0 else "#F4E9E4",
             fontsize=8.5)
        if i < len(steps) - 1:
            _arrow(ax, 3.0, y, 3.0, y - 0.45, color=NAVY)
        y -= 1.3
    _save(fig, "fig3_flow.png")


def _route_solution(campus, config, ctx):
    solution, _ = solve_routing(ctx, method="savings_2opt", seed=1)
    return solution


def _alns_solution(campus, config, ctx):
    initial, _ = solve_routing(ctx, method="savings_2opt", seed=1)
    result = alns(
        ctx.routing,
        initial,
        ALNSParams(iterations=500, seed=1, time_limit_s=5.0),
    )
    return result.best


def fig_cli(campus, config, ctx):
    solution = _route_solution(campus, config, ctx)
    m = solution.metrics
    font_path = Path("C:/Windows/Fonts/consola.ttf")
    font = ImageFont.truetype(str(font_path), 22) if font_path.exists() else ImageFont.load_default()
    title_font = ImageFont.truetype(str(font_path), 26) if font_path.exists() else font
    img = Image.new("RGB", (1300, 760), "#1E1E1E")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1300, 48], fill="#323233")
    d.text((20, 12), "Campus Express v1  -  terminal", font=title_font, fill="#CCCCCC")
    lines = [
        ("$ python run.py solve --packages data/packages_500.json --method savings_2opt", "#4EC9B0"),
        ("", "#D4D4D4"),
        ("[load]  campus = HeNan Polytechnic (simulated)", "#D4D4D4"),
        ("[load]  packages = 500, tasks = 96, couriers = 4", "#D4D4D4"),
        ("[sort]  method = cap_ls, overflow = 0, chutes = 10", "#D4D4D4"),
        ("[route] method = savings_2opt", "#D4D4D4"),
        ("", "#D4D4D4"),
        (f"[result] feasible = {m.get('feasible', 0):.0f}", "#DCDCAA"),
        (f"[result] distance_km = {m.get('distance_km', 0):.2f}", "#D4D4D4"),
        (f"[result] makespan_min = {m.get('makespan_min', 0):.1f}", "#D4D4D4"),
        (f"[result] on_time_rate = {m.get('on_time_rate', 0):.3f}", "#D4D4D4"),
        (f"[result] unassigned = {m.get('unassigned', 0):.0f}", "#D4D4D4"),
        (f"[result] load_cv = {m.get('load_cv', 0):.3f}", "#D4D4D4"),
        ("[write] results/solve_500.json", "#4EC9B0"),
        ("$ ", "#4EC9B0"),
    ]
    y = 80
    for text, color in lines:
        d.text((24, y), text, font=font, fill=color)
        y += 42
    img.save(OUT / "fig3_cli.png")
    print("wrote", OUT / "fig3_cli.png")


def fig_sorting(campus, assignment):
    _chinese()
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.5), gridspec_kw={"width_ratios": [1.35, 1]})
    ax = axes[0]
    for pid, point in campus.points.items():
        c = CLUSTER_COLORS[assignment.labels[pid] % len(CLUSTER_COLORS)]
        ax.scatter(point.x_m, point.y_m, s=40, color=c, edgecolor="white", linewidth=0.6, zorder=2)
        ax.text(point.x_m + 12, point.y_m + 10, pid, fontsize=6, color="#333333")
    ax.scatter(campus.center.x_m, campus.center.y_m, marker="*", s=200, color=RED,
               edgecolor="white", zorder=4)
    ax.set_aspect("equal")
    ax.set_title("最终分区（10 个格口）", fontsize=10)
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    _tidy(ax, grid_axis=None)

    ax = axes[1]
    colors = [CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(len(assignment.loads))]
    ax.bar(range(1, len(assignment.loads) + 1), assignment.loads, color=colors, zorder=2)
    ax.axhline(60, color=RED, linestyle="--", linewidth=1.1, label="容量 60")
    ax.set_xlabel("格口编号")
    ax.set_ylabel("包裹数")
    ax.set_title("格口负载与容量", fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    _tidy(ax)
    fig.tight_layout()
    _save(fig, "fig4_sorting.png")


def fig_routes(campus, ctx, solution):
    _chinese()
    fig, ax = plt.subplots(figsize=(7.2, 5.7))
    for edge in campus.edges:
        x1, y1 = campus.nodes[edge.u]
        x2, y2 = campus.nodes[edge.v]
        ax.plot([x1, x2], [y1, y2], color="#E1E4E7", linewidth=0.6, zorder=1)
    colors = [NAVY, RED, GREEN, SAND]
    for idx, route in enumerate(solution.routes):
        if not route.task_ids:
            continue
        xs = [campus.center.x_m]
        ys = [campus.center.y_m]
        for tid in route.task_ids:
            pid = ctx.routing.tasks[tid].point_id
            x, y = campus.point_xy(pid)
            xs.append(x)
            ys.append(y)
        xs.append(campus.center.x_m)
        ys.append(campus.center.y_m)
        ax.plot(xs, ys, color=colors[idx % len(colors)], linewidth=1.8, alpha=0.9,
                marker="o", markersize=3.2, zorder=3, label=f"快递员 {idx + 1}")
    ax.scatter(campus.center.x_m, campus.center.y_m, marker="*", s=240, color=RED,
               edgecolor="white", zorder=5)
    ax.set_aspect("equal")
    ax.set_xlabel("x / m")
    ax.set_ylabel("y / m")
    ax.set_title("ALNS 的 4 条配送路线（500 件）", fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    _tidy(ax, grid_axis=None)
    _save(fig, "fig4_routes.png")


def fig_compare(summary):
    _english()
    methods = ["nn", "insertion", "savings", "savings_2opt", "alns"]
    labels = ["NN+EDD", "Insertion", "Savings", "Savings+2opt", "ALNS"]
    scale = 500
    dist = [_metric(summary, "E2", scale, m, "distance_km") for m in methods]
    mk = [_metric(summary, "E2", scale, m, "makespan_min") for m in methods]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.2))
    x = np.arange(len(methods))
    axes[0].bar(x, dist, color=[GREY, GREY, LIGHT, NAVY, RED], zorder=2)
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    axes[0].set_ylabel("Distance (km)")
    axes[0].set_title("Total distance (500 packages)")
    for xi, v in zip(x, dist):
        axes[0].text(xi, v + 0.4, f"{v:.1f}", ha="center", fontsize=7)
    _tidy(axes[0])
    axes[1].bar(x, mk, color=[GREY, GREY, LIGHT, NAVY, RED], zorder=2)
    axes[1].set_xticks(x)
    axes[1].set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    axes[1].set_ylabel("Makespan (min)")
    axes[1].set_title("Makespan (500 packages)")
    for xi, v in zip(x, mk):
        axes[1].text(xi, v + 5, f"{v:.0f}", ha="center", fontsize=7)
    _tidy(axes[1])
    fig.subplots_adjust(left=0.09, right=0.98, bottom=0.30, top=0.88, wspace=0.30)
    _save(fig, "fig4_compare.png", tight=False)


def fig_runtime(summary):
    _english()
    scales = [100, 300, 500]
    fig, ax = plt.subplots(figsize=(5.8, 3.4))
    for method, label, color, marker in [
        ("savings_2opt", "Savings+2opt", NAVY, "o"),
        ("alns", "ALNS", RED, "s"),
    ]:
        vals = [_metric(summary, "E2", s, method, "runtime_s") for s in scales]
        ax.plot(scales, vals, marker=marker, color=color, linewidth=1.8, label=label)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Packages")
    ax.set_ylabel("Runtime (s)")
    ax.set_title("Runtime vs instance size")
    ax.legend(frameon=False, fontsize=8)
    _tidy(ax)
    fig.tight_layout()
    _save(fig, "fig4_runtime.png")


def fig_convergence():
    _english()
    files = sorted((RESULTS / "convergence").glob("convergence_500_*.json"))
    if not files:
        files = sorted((RESULTS / "convergence").glob("convergence_100_*.json"))
    if not files:
        print("no convergence files; skip")
        return
    fig, ax = plt.subplots(figsize=(6.2, 3.4))
    curves = []
    for path in files:
        with open(path, "r", encoding="utf-8") as fh:
            curve = json.load(fh)
        curves.append(curve)
        ax.plot(range(len(curve)), curve, color=GREY, linewidth=0.9, alpha=0.45)
    if curves:
        n = min(len(c) for c in curves)
        arr = np.asarray([c[:n] for c in curves], dtype=float)
        mean = np.nanmean(arr, axis=0)
        std = np.nanstd(arr, axis=0)
        ax.plot(range(n), mean, color=RED, linewidth=2.0, label="mean")
        ax.fill_between(range(n), mean - std, mean + std, color=RED, alpha=0.15, label="±1 std")
    ax.set_xlabel("Iteration")
    ax.set_ylabel("Best objective")
    ax.set_title("ALNS convergence (500 packages)")
    ax.legend(frameon=False, fontsize=8)
    _tidy(ax)
    fig.tight_layout()
    _save(fig, "fig4_convergence.png")


def fig_gantt(ctx, solution):
    _english()
    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    for courier in ctx.routing.couriers:
        schedule = ctx.routing.schedule_route(courier.id, solution.routes[courier.id].task_ids)
        for tid in solution.routes[courier.id].task_ids:
            task = ctx.routing.tasks[tid]
            start = schedule.arrivals[tid]
            end = schedule.departures[tid]
            ax.add_patch(Rectangle((start, courier.id - 0.18), max(0.1, end - start), 0.36,
                                   color=RED if task.priority == Priority.EXPRESS else
                                   (SAND if task.priority == Priority.URGENT else NAVY),
                                   alpha=0.75, linewidth=0))
            ax.add_patch(Rectangle((task.window.start_min, courier.id - 0.32),
                                   task.window.duration, 0.64,
                                   color="#E8E8E8", alpha=0.12, linewidth=0))
    ax.set_yticks(range(len(ctx.routing.couriers)))
    ax.set_yticklabels([f"Courier {c.id + 1}" for c in ctx.routing.couriers])
    ax.set_xlim(480, 1080)
    ax.set_xlabel("Time (minutes after midnight)")
    ax.set_ylabel("Courier")
    ax.set_title("ALNS delivery schedule and time windows (500 packages)")
    handles = [
        plt.Line2D([], [], color=RED, label="Express"),
        plt.Line2D([], [], color=SAND, label="Urgent"),
        plt.Line2D([], [], color=NAVY, label="Normal"),
    ]
    ax.legend(handles=handles, frameon=False, fontsize=8, loc="upper right")
    _tidy(ax, grid_axis="x")
    fig.tight_layout()
    _save(fig, "fig4_gantt.png")


def main():
    campus, config, ctx = _data()
    assignment = solve_sorting(ctx, method="cap_ls", seed=1)
    solution = _route_solution(campus, config, ctx)
    alns_solution = _alns_solution(campus, config, ctx)
    summary = _summary()

    fig_campus(campus)
    fig_architecture()
    fig_iteration()
    fig_kmeans_capacity(campus, assignment)
    fig_savings()
    fig_flow()
    fig_cli(campus, config, ctx)
    fig_sorting(campus, assignment)
    fig_routes(campus, ctx, alns_solution)
    if summary:
        fig_compare(summary)
        fig_runtime(summary)
    fig_convergence()
    fig_gantt(ctx, alns_solution)


if __name__ == "__main__":
    main()
