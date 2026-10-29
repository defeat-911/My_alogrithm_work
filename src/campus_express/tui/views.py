"""Pure Rich renderables for the v2 terminal interface.

Nothing here prints or reads input; ``app.py`` owns the console.  Keeping the
views pure makes them easy to render into a StringIO in tests.
"""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Sequence

from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from ..models import Priority, format_hhmm
from .state import (
    DatasetInfo,
    DatasetSummary,
    ROUTING_METHODS,
    RunRecord,
    SORTING_METHODS,
    UIState,
)

CYAN = "bold cyan"
DIM = "dim"
GREEN = "green"
YELLOW = "yellow"
RED = "bold red"

PRIORITY_LABELS = {
    Priority.NORMAL: ("普通", "dim"),
    Priority.URGENT: ("加急", "yellow"),
    Priority.EXPRESS: ("特急", "bold red"),
}

RUN_KIND_LABELS = {
    "sorting": "分拣",
    "routing": "路径",
    "solve": "一键",
}

METRIC_LABELS = {
    "feasible": "可行",
    "n_packages": "包裹数",
    "n_tasks": "任务数",
    "n_points": "点位数",
    "n_routes": "路线数",
    "distance_km": "总距离",
    "distance_m": "总距离",
    "makespan_min": "完工时间",
    "on_time_rate": "准时率",
    "tardiness_min": "迟到",
    "waiting_min": "等待",
    "priority_weighted_arrival": "优先级加权到达",
    "load_cv": "负载变异系数",
    "max_load_ratio": "最大负载率",
    "overflow_packages": "溢出包裹",
    "empty_clusters": "空格口",
    "unassigned": "未分配任务",
    "objective": "目标值",
    "runtime_s": "运行时间",
    "tsp_proxy_m": "簇内路线代理",
    "silhouette": "轮廓系数",
    "alns_iterations": "ALNS 迭代",
}

SORTING_KEYS = [
    "objective",
    "tsp_proxy_m",
    "load_cv",
    "max_load_ratio",
    "overflow_packages",
    "empty_clusters",
    "silhouette",
    "n_points",
    "n_packages",
    "runtime_s",
]

ROUTING_KEYS = [
    "feasible",
    "distance_km",
    "makespan_min",
    "on_time_rate",
    "tardiness_min",
    "waiting_min",
    "priority_weighted_arrival",
    "load_cv",
    "unassigned",
    "n_routes",
    "n_tasks",
    "objective",
    "runtime_s",
    "alns_iterations",
]


def render_header(state: UIState) -> RenderableType:
    heading = Text()
    heading.append("校园快递智能分拣与路径规划", style="bold bright_cyan")
    heading.append("  · 控制台", style=DIM)
    subtitle = state.campus.name if state.campus is not None else "未加载校园"
    return Panel(
        heading,
        subtitle=subtitle,
        border_style="cyan",
        padding=(0, 1),
        title_align="left",
    )


def render_status_bar(state: UIState) -> RenderableType:
    ctx = state.ctx
    packages = len(ctx.packages) if ctx is not None else "—"
    tasks = len(ctx.tasks) if ctx is not None else "—"
    chutes = len(ctx.campus.chutes) if ctx is not None else "—"
    quick = "开" if state.quick else "关"
    windows = "硬" if state.hard_windows else "软"
    line1 = Text.assemble(
        ("数据 ", DIM),
        (state.packages_label, "cyan"),
        ("  |  包裹/任务 ", DIM),
        (f"{packages}/{tasks}", "bold"),
        ("  |  快递员 ", DIM),
        (str(state.effective_couriers()), "bold"),
        ("  |  格口 ", DIM),
        (str(chutes), "bold"),
    )
    line2 = Text.assemble(
        ("分拣 ", DIM),
        (state.sorting_method, "cyan"),
        ("  |  路径 ", DIM),
        (state.routing_method, "cyan"),
        ("  |  快速 ", DIM),
        (quick, GREEN if state.quick else YELLOW),
        ("  |  时间窗 ", DIM),
        (windows, "cyan"),
        ("  |  ", DIM),
        (state.status, state.status_style),
    )
    return Group(line1, line2)


def render_footer(text: str) -> RenderableType:
    return Rule(Text(text, style=DIM), style=DIM)


def render_error(message: str) -> RenderableType:
    return Panel(Text(message, style=RED), title="错误", border_style="red", padding=(0, 1))


def render_info(message: str) -> RenderableType:
    return Panel(Text(message, style="cyan"), border_style="cyan", padding=(0, 1))


def render_menu(
    title: str,
    options: Sequence[tuple[str, str]],
    current: str | None = None,
) -> RenderableType:
    table = Table.grid(padding=(0, 1))
    table.add_column(justify="right", width=3, style="bold bright_white")
    table.add_column(style="cyan")
    for key, label in options:
        marker = "  ← 当前" if current is not None and key == current else ""
        table.add_row(key, Text(label + marker, style="bold" if marker else "cyan"))
    return Panel(table, title=title, border_style="cyan", padding=(0, 1))


def render_home(state: UIState, width: int | None = None) -> RenderableType:
    left = render_menu(
        "主菜单",
        [
            ("1", "数据管理"),
            ("2", "分拣优化"),
            ("3", "路径规划"),
            ("4", "一键求解"),
            ("5", "结果查看"),
            ("6", "导出 / 设置"),
            ("0", "退出"),
        ],
    )
    right = _render_overview(state)
    if width is not None and width < 90:
        return Group(left, right)
    grid = Table.grid(expand=True, padding=(0, 1))
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(left, right)
    return grid


def _render_overview(state: UIState) -> RenderableType:
    table = Table.grid(padding=(0, 1))
    table.add_column(style=DIM, width=14)
    table.add_column(style="white")
    ctx = state.ctx
    table.add_row("数据", state.packages_label)
    table.add_row(
        "包裹 / 任务",
        f"{len(ctx.packages)} / {len(ctx.tasks)}" if ctx is not None else "—",
    )
    table.add_row("快递员", str(state.effective_couriers()))
    sort_record = state.last_solve or state.last_sorting
    route_record = state.last_solve or state.last_routing
    if sort_record is not None and sort_record.assignment is not None:
        metrics = sort_record.assignment.metrics
        table.add_row(
            "分拣结果",
            Text(
                f"{sort_record.method} · CV {metrics.get('load_cv', 0.0):.3f}"
                f" · 溢出 {metrics.get('overflow_packages', 0.0):.0f}"
                f" · {sort_record.runtime_s:.1f} s",
                style=GREEN,
            ),
        )
    else:
        table.add_row("分拣结果", Text("未运行", style=DIM))
    if route_record is not None and route_record.solution is not None:
        metrics = route_record.solution.metrics
        table.add_row(
            "路径结果",
            Text(
                f"{route_record.method} · {metrics.get('distance_km', 0.0):.2f} km"
                f" · 准时 {metrics.get('on_time_rate', 0.0) * 100:.1f}%"
                f" · 未分配 {metrics.get('unassigned', 0.0):.0f}",
                style=GREEN if metrics.get("feasible", 0.0) else YELLOW,
            ),
        )
    else:
        table.add_row("路径结果", Text("未运行", style=DIM))
    if state.last_run is not None:
        table.add_row(
            "最近运行",
            f"{RUN_KIND_LABELS.get(state.last_run.kind, state.last_run.kind)}"
            f" · {state.last_run.method} · {state.last_run.runtime_s:.2f} s",
        )
    else:
        table.add_row("最近运行", Text("尚未运行", style=DIM))
    table.add_row(
        "最近导出",
        str(state.last_export_path) if state.last_export_path else "—",
    )
    return Panel(table, title="当前状态", border_style="cyan", padding=(0, 1))


def render_dataset_list(
    datasets: Sequence[DatasetInfo], current: Path | None
) -> RenderableType:
    if not datasets:
        return Panel(
            Text("data/ 下没有 packages_*.json；按 g 生成新数据。", style=YELLOW),
            title="可用数据",
            border_style="cyan",
            padding=(0, 1),
        )
    table = Table(
        title="可用数据",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        show_edge=False,
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("文件")
    table.add_column("包裹", justify="right")
    table.add_column("种子", justify="right")
    table.add_column("状态")
    for index, info in enumerate(datasets, start=1):
        is_current = current is not None and info.path == current
        name = info.path.name + ("  *" if is_current else "")
        count = str(info.n_packages) if info.n_packages is not None else "—"
        seed = str(info.seed) if info.seed is not None else "—"
        if info.error:
            status = Text("读取失败", style=RED)
        elif is_current:
            status = Text("当前", style=GREEN)
        else:
            status = Text("正常", style=DIM)
        table.add_row(str(index), name, count, seed, status)
    return Panel(table, border_style="cyan", padding=(0, 1))


def _capacity_text(value: object) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def render_validation(summary: DatasetSummary) -> RenderableType:
    validation = summary.validation
    table = Table.grid(padding=(0, 1))
    table.add_column(style=DIM, width=16)
    table.add_column()
    table.add_row("文件", summary.path.name)
    table.add_row("包裹 / 任务", f"{summary.n_packages} / {summary.n_tasks}")
    table.add_row("结构校验", Text("通过", style=GREEN))
    feasible = bool(validation.get("feasible", False))
    table.add_row(
        "容量校验",
        Text("可行" if feasible else "不可行", style=GREEN if feasible else RED),
    )
    table.add_row("总重量", f"{float(validation.get('total_weight_kg', 0.0)):.2f} kg")
    table.add_row("格口容量", _capacity_text(validation.get("chute_capacity", "—")))
    table.add_row(
        "快递员容量",
        f"{_capacity_text(validation.get('courier_capacity_packages', '—'))} 件 / "
        f"{_capacity_text(validation.get('courier_capacity_kg', '—'))} kg",
    )
    table.add_row(
        "单点最大需求",
        _capacity_text(validation.get("max_point_demand", "—")),
    )
    parts: list[RenderableType] = [table]
    reasons = validation.get("reasons", [])
    if reasons:
        parts.append(Text("不可行原因：", style=RED))
        for reason in reasons:
            parts.append(Text(f"  · {reason}", style=YELLOW))
    if summary.generated:
        parts.append(Text("（本次会话新生成）", style=DIM))
    return Panel(Group(*parts), title="数据概览", border_style="cyan", padding=(0, 1))


def render_method_menu(kind: str, current: str) -> RenderableType:
    rows = SORTING_METHODS if kind == "sorting" else ROUTING_METHODS
    title = "分拣方法" if kind == "sorting" else "路径方法"
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        show_edge=False,
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("方法")
    table.add_column("说明")
    table.add_column("当前", justify="center", width=6)
    for index, (name, label, description) in enumerate(rows, start=1):
        table.add_row(
            str(index),
            label,
            description,
            Text("●", style=GREEN) if name == current else "",
        )
    hint = (
        "提示：cap_ls 局部搜索最多约 5 秒；其余分拣方法通常较快。"
        if kind == "sorting"
        else "提示：ALNS 快速模式最多约 3 秒；完整模式最多约 30 秒。"
    )
    return Panel(
        Group(table, Text(hint, style=DIM)),
        title=title,
        border_style="cyan",
        padding=(0, 1),
    )


def _metric_value(key: str, value: object) -> Text:
    if key == "feasible":
        ok = bool(value)
        return Text("是" if ok else "否", style=GREEN if ok else RED)
    if isinstance(value, float) and not math.isfinite(value):
        return Text("—", style=YELLOW)
    try:
        if key in {"distance_km"}:
            return Text(f"{float(value):.2f} km")
        if key == "distance_m":
            return Text(f"{float(value) / 1000.0:.2f} km")
        if key in {"makespan_min", "tardiness_min", "waiting_min"}:
            return Text(f"{float(value):.1f} min")
        if key == "on_time_rate":
            return Text(f"{float(value) * 100.0:.1f}%")
        if key == "priority_weighted_arrival":
            return Text(f"{float(value):.1f}")
        if key == "load_cv":
            return Text(f"{float(value):.3f}")
        if key == "max_load_ratio":
            return Text(f"{float(value) * 100.0:.1f}%")
        if key in {"objective", "silhouette"}:
            return Text(f"{float(value):.3f}")
        if key == "runtime_s":
            return Text(f"{float(value):.2f} s")
        if key == "tsp_proxy_m":
            return Text(f"{float(value) / 1000.0:.2f} km")
        if key in {
            "n_packages",
            "n_tasks",
            "n_points",
            "n_routes",
            "unassigned",
            "overflow_packages",
            "empty_clusters",
            "alns_iterations",
        }:
            return Text(str(int(float(value))))
    except (TypeError, ValueError):
        pass
    return Text(str(value))


def metrics_table(title: str, metrics: dict, kind: str) -> Table:
    keys = SORTING_KEYS if kind == "sorting" else ROUTING_KEYS
    table = Table(
        title=title,
        box=box.SIMPLE,
        header_style="bold cyan",
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("指标", style=DIM)
    table.add_column("值", justify="right")
    for key in keys:
        if key in metrics and key in METRIC_LABELS:
            table.add_row(METRIC_LABELS[key], _metric_value(key, metrics[key]))
    return table


def chute_table(ctx, assignment) -> RenderableType:
    chute_ids = sorted(ctx.campus.chutes)
    point_counts = Counter(assignment.labels.values())
    table = Table(
        title="格口负载",
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        show_edge=False,
    )
    table.add_column("格口")
    table.add_column("名称")
    table.add_column("包裹", justify="right")
    table.add_column("点位", justify="right")
    table.add_column("容量比", justify="right")
    table.add_column("状态", justify="center")
    for index, chute_id in enumerate(chute_ids):
        chute = ctx.campus.chutes[chute_id]
        load = assignment.loads[index] if index < len(assignment.loads) else 0
        capacity = max(1, int(chute.capacity_packages))
        ratio = load / capacity
        if ratio > 1.0:
            ratio_style, status = RED, "溢出"
        elif ratio > 0.9:
            ratio_style, status = YELLOW, "接近"
        else:
            ratio_style, status = GREEN, "正常"
        table.add_row(
            chute_id,
            chute.name,
            str(load),
            str(point_counts.get(index, 0)),
            Text(f"{ratio * 100:.0f}%", style=ratio_style),
            Text(status, style=ratio_style),
        )
    capacity = min(
        int(chute.capacity_packages) for chute in ctx.campus.chutes.values()
    )
    summary = Text.assemble(
        ("最大负载率 ", DIM),
        (f"{assignment.max_load_ratio(capacity) * 100:.1f}%", "bold"),
        ("  |  溢出包裹 ", DIM),
        (str(assignment.overflow(capacity)), "bold"),
        ("  |  空格口 ", DIM),
        (str(assignment.empty_clusters()), "bold"),
    )
    return Group(table, summary)


def _safe_hhmm(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return format_hhmm(value)


def courier_table(ctx, record: RunRecord) -> RenderableType:
    solution = record.solution
    if solution is None:
        return render_info("没有路径结果。")
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        show_edge=False,
    )
    table.add_column("快递员", justify="center")
    table.add_column("停靠", justify="right")
    table.add_column("包裹", justify="right")
    table.add_column("载重", justify="right")
    table.add_column("距离", justify="right")
    table.add_column("结束", justify="right")
    table.add_column("状态", justify="center")
    routes = {route.courier_id: route for route in solution.routes}
    for courier in ctx.routing.couriers:
        schedule = record.schedules.get(courier.id)
        route = routes.get(courier.id)
        if route is None or schedule is None or not route.task_ids:
            table.add_row(
                str(courier.id + 1),
                "0",
                "0",
                "—",
                "—",
                "—",
                Text("空闲", style=DIM),
            )
            continue
        if not schedule.feasible:
            status = Text("不可行", style=RED)
        elif schedule.tardiness_min > 1e-9:
            status = Text(f"迟到 {schedule.tardiness_min:.1f}", style=YELLOW)
        else:
            status = Text("正常", style=GREEN)
        table.add_row(
            str(courier.id + 1),
            str(len(route.task_ids)),
            str(schedule.load),
            f"{schedule.weight_kg:.2f} kg",
            f"{schedule.distance_m / 1000.0:.2f} km",
            _safe_hhmm(schedule.end_time),
            status,
        )
    subtitle = (
        f"未分配任务 {len(solution.unassigned)}" if solution.unassigned else ""
    )
    return Panel(
        table,
        title="路线汇总",
        subtitle=subtitle or None,
        border_style="cyan",
        padding=(0, 1),
    )


def render_sorting_result(ctx, record: RunRecord) -> RenderableType:
    if record.assignment is None:
        return render_info("没有分拣结果。")
    metrics = dict(record.assignment.metrics)
    metrics["runtime_s"] = record.runtime_s
    return Group(
        metrics_table("分拣指标", metrics, "sorting"),
        chute_table(ctx, record.assignment),
    )


def render_routing_result(ctx, record: RunRecord) -> RenderableType:
    solution = record.solution
    if solution is None:
        return render_info("没有路径结果。")
    metrics = dict(solution.metrics)
    metrics["n_packages"] = len(ctx.packages)
    metrics["n_tasks"] = len(ctx.tasks)
    metrics["runtime_s"] = record.runtime_s
    if record.alns is not None:
        metrics["alns_iterations"] = record.alns.iterations
    parts: list[RenderableType] = [
        metrics_table("路径指标", metrics, "routing"),
        courier_table(ctx, record),
    ]
    if record.alns is not None:
        parts.append(convergence_panel(record.alns, record.runtime_s))
    return Group(*parts)


def render_solve_result(ctx, record: RunRecord) -> RenderableType:
    return Group(
        render_sorting_result(ctx, record),
        render_routing_result(ctx, record),
    )


def render_results(state: UIState) -> RenderableType:
    ctx = state.ctx
    if ctx is None or not state.has_results:
        return render_info("还没有结果；先运行分拣、路径或一键求解。")
    if state.last_solve is not None:
        return render_solve_result(ctx, state.last_solve)
    parts: list[RenderableType] = []
    if state.last_sorting is not None:
        parts.append(render_sorting_result(ctx, state.last_sorting))
    if state.last_routing is not None:
        parts.append(render_routing_result(ctx, state.last_routing))
    if not parts:
        return render_info("还没有结果；先运行分拣、路径或一键求解。")
    return Group(*parts)


def render_route_detail(ctx, record: RunRecord, courier_id: int) -> RenderableType:
    schedule = record.schedules.get(courier_id)
    if schedule is None:
        return render_info("该快递员没有路线记录。")
    if not schedule.task_ids:
        return render_info(f"快递员 {courier_id + 1} 没有任务。")
    table = Table(
        box=box.SIMPLE_HEAVY,
        header_style="bold cyan",
        show_edge=False,
    )
    table.add_column("#", justify="right", width=3)
    table.add_column("配送点")
    table.add_column("时间窗")
    table.add_column("优先级")
    table.add_column("包裹", justify="right")
    table.add_column("到达", justify="right")
    table.add_column("等待", justify="right")
    table.add_column("状态", justify="center")
    for index, tid in enumerate(schedule.task_ids, start=1):
        task = ctx.routing.tasks[tid]
        point = ctx.campus.points.get(task.point_id)
        arrival = schedule.arrivals.get(tid)
        wait = schedule.waits.get(tid, 0.0)
        if arrival is not None and math.isfinite(arrival):
            arrival_text = _safe_hhmm(arrival)
            late = arrival > task.window.end_min + 1e-9
        else:
            arrival_text = "—"
            late = not schedule.feasible
        if late:
            status = Text("迟到", style=RED)
        elif wait > 0.5:
            status = Text("等待", style=YELLOW)
        else:
            status = Text("正常", style=GREEN)
        priority_label, priority_style = PRIORITY_LABELS.get(
            task.priority, (str(task.priority), DIM)
        )
        table.add_row(
            str(index),
            point.name if point is not None else task.point_id,
            str(task.window),
            Text(priority_label, style=priority_style),
            str(task.demand),
            arrival_text,
            f"{wait:.1f} min",
            status,
        )
    subtitle = (
        f"{schedule.distance_m / 1000.0:.2f} km · "
        f"结束 {_safe_hhmm(schedule.end_time)} · "
        f"载重 {schedule.weight_kg:.2f} kg"
    )
    return Panel(
        table,
        title=f"快递员 {courier_id + 1} 路线明细",
        subtitle=subtitle,
        border_style="cyan",
        padding=(0, 1),
    )


def _quick_iterations(state: UIState) -> int:
    cfg = state.config.get("routing", {})
    key = "alns_quick_iterations" if state.quick else "alns_iterations"
    return int(cfg.get(key, 300 if state.quick else 2000))


def _quick_mode_text(state: UIState) -> str:
    if state.quick:
        return "开（最多约 3 秒）"
    return f"关（ALNS {_quick_iterations(state)} 次）"


def render_settings(state: UIState) -> RenderableType:
    table = Table.grid(padding=(0, 1))
    table.add_column(style=DIM, width=14)
    table.add_column()
    table.add_row("数据文件", state.packages_label)
    table.add_row("快递员数", str(state.effective_couriers()))
    table.add_row("随机种子", str(state.seed))
    table.add_row(
        "快速模式",
        Text(
            _quick_mode_text(state),
            style=GREEN if state.quick else YELLOW,
        ),
    )
    table.add_row(
        "时间窗",
        Text("硬约束" if state.hard_windows else "软约束", style="cyan"),
    )
    table.add_row("分拣方法", state.sorting_method)
    table.add_row("路径方法", state.routing_method)
    results = []
    if state.last_sorting is not None:
        results.append(f"分拣 {state.last_sorting.method}")
    if state.last_routing is not None:
        results.append(f"路径 {state.last_routing.method}")
    if state.last_solve is not None:
        results.append(f"一键 {state.last_solve.method}")
    table.add_row("结果", " · ".join(results) if results else "未运行")
    table.add_row(
        "最近导出",
        str(state.last_export_path) if state.last_export_path else "—",
    )
    return Panel(table, title="导出 / 设置", border_style="cyan", padding=(0, 1))


def render_solve_confirm(state: UIState) -> RenderableType:
    table = Table.grid(padding=(0, 1))
    table.add_column(style=DIM, width=14)
    table.add_column()
    table.add_row("数据文件", state.packages_label)
    table.add_row("分拣方法", state.sorting_method)
    table.add_row("路径方法", state.routing_method)
    table.add_row("随机种子", str(state.seed))
    table.add_row("快递员数", str(state.effective_couriers()))
    table.add_row(
        "快速模式",
        Text("开" if state.quick else "关", style=GREEN if state.quick else YELLOW),
    )
    table.add_row(
        "时间窗",
        Text("硬约束" if state.hard_windows else "软约束", style="cyan"),
    )
    return Panel(
        Group(table, Text("按 Enter 开始；b 返回。", style=DIM)),
        title="一键求解",
        border_style="cyan",
        padding=(0, 1),
    )


def convergence_panel(alns, total_runtime_s: float) -> RenderableType:
    convergence = [float(value) for value in alns.convergence if math.isfinite(value)]
    if not convergence:
        return render_info("ALNS 没有返回收敛数据。")
    initial = convergence[0]
    final = convergence[-1]
    improvement = ((initial - final) / initial * 100.0) if initial else 0.0
    line1 = Text.assemble(
        ("迭代 ", DIM),
        (str(alns.iterations), "bold"),
        ("  |  ALNS 用时 ", DIM),
        (f"{alns.runtime_s:.2f} s", "bold"),
        ("  |  总用时 ", DIM),
        (f"{total_runtime_s:.2f} s", "bold"),
    )
    line2 = Text.assemble(
        ("目标 ", DIM),
        (f"{initial:.3f}", "bold"),
        (" → ", DIM),
        (f"{final:.3f}", "bold"),
        ("  |  改进 ", DIM),
        (f"{improvement:.2f}%", GREEN if improvement > 0 else YELLOW),
    )
    line3 = Text.assemble(("收敛 ", DIM), (sparkline(convergence), "cyan"))
    return Panel(Group(line1, line2, line3), title="ALNS 收敛", border_style="cyan", padding=(0, 1))


def sparkline(values: Sequence[float], width: int = 60) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    clean = [float(value) for value in values if math.isfinite(value)]
    if not clean:
        return ""
    if width <= 0:
        width = len(clean)
    if len(clean) > width:
        if width == 1:
            sampled = [clean[-1]]
        else:
            step = (len(clean) - 1) / (width - 1)
            sampled = [clean[round(index * step)] for index in range(width)]
    else:
        sampled = clean
    low, high = min(sampled), max(sampled)
    if high - low < 1e-12:
        return blocks[0] * len(sampled)
    scale = (len(blocks) - 1) / (high - low)
    return "".join(blocks[int((value - low) * scale)] for value in sampled)
