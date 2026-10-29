"""State and actions for the v2 Rich terminal interface.

This module deliberately has no Rich imports: it is plain Python so the UI
state can be unit-tested without a terminal.  Rendering lives in ``views.py``
and input/navigation lives in ``app.py``.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from ..data_gen import check_instance, generate_packages, save_dataset
from ..io import load_campus, load_config, load_packages, validate_packages
from ..models import Campus, Solution
from ..routing.alns import ALNSResult
from ..routing.common import Schedule
from ..solver import (
    PipelineContext,
    PipelineResult,
    build_context_from_data,
    solve_routing,
    solve_sorting,
)
from ..sorting.common import Assignment

SORTING_METHODS: tuple[tuple[str, str, str], ...] = (
    ("grid", "网格分区", "按坐标网格划分，基线"),
    ("sweep", "扫描分区", "按极角扫描，基线"),
    ("kmeans", "K-Means++", "空间聚类，不考虑容量"),
    ("cap_kmeans", "容量约束 K-Means", "需求加权 + 容量感知"),
    ("cap_ls", "容量约束 + 局部搜索", "默认；relocate/swap，最多约 5 秒"),
)

ROUTING_METHODS: tuple[tuple[str, str, str], ...] = (
    ("nn", "最近邻 + EDD", "短视基线"),
    ("insertion", "最小增量插入", "cheapest insertion"),
    ("savings", "Clarke-Wright", "节约值合并"),
    ("savings_2opt", "Savings + 2-opt", "帧内 2-opt/Or-opt"),
    ("alns", "ALNS", "默认；自适应大邻域搜索"),
)

SORTING_METHOD_NAMES = {row[0] for row in SORTING_METHODS}
ROUTING_METHOD_NAMES = {row[0] for row in ROUTING_METHODS}
QUICK_ALNS_TIME_LIMIT_S = 3.0


class TUIError(RuntimeError):
    """An error that should be shown to the user, not a traceback."""


@dataclass
class DatasetInfo:
    """Cheap metadata for the data-selection screen."""

    path: Path
    n_packages: int | None
    seed: int | None = None
    error: str | None = None


@dataclass
class DatasetSummary:
    """Result of loading and validating a package file."""

    path: Path
    n_packages: int
    n_tasks: int
    validation: dict[str, Any]
    structurally_valid: bool = True
    generated: bool = False

    @property
    def feasible(self) -> bool:
        return bool(self.validation.get("feasible", False))


@dataclass
class RunRecord:
    """One sorting, routing or combined run."""

    kind: Literal["sorting", "routing", "solve"]
    method: str
    seed: int
    quick: bool
    runtime_s: float
    created_at: datetime
    assignment: Assignment | None = None
    solution: Solution | None = None
    alns: ALNSResult | None = None
    schedules: dict[int, Schedule] = field(default_factory=dict)
    result: PipelineResult | None = None


def find_repo_root(start: str | Path | None = None) -> Path:
    """Find the repository root by looking for the data and config files."""

    base = Path(start).resolve() if start is not None else Path(__file__).resolve()
    candidates = [base, *base.parents] if base.is_dir() else list(base.parents)
    for candidate in candidates:
        if (candidate / "data" / "campus.json").exists() and (
            candidate / "config" / "default.yaml"
        ).exists():
            return candidate
    return Path.cwd().resolve()


def _resolve_user_path(value: str | Path | None, default: Path) -> Path:
    """Defaults live under the repo root; explicit relative paths use cwd."""

    if value is None:
        return default
    path = Path(value)
    return path if path.is_absolute() else (Path.cwd() / path)


def _dataset_sort_key(path: Path) -> tuple[int, str]:
    digits = "".join(ch for ch in path.stem if ch.isdigit())
    return (int(digits) if digits else 10**9, path.name)


def choose_default_dataset(data_dir: Path) -> Path | None:
    """Prefer the canonical 300-package file, then 100, then numeric order."""

    for name in ("packages_300.json", "packages_100.json"):
        candidate = data_dir / name
        if candidate.exists():
            return candidate
    files = sorted(data_dir.glob("packages_*.json"), key=_dataset_sort_key)
    return files[0] if files else None


def discover_datasets(data_dir: Path) -> list[DatasetInfo]:
    """Read lightweight metadata for every ``packages_*.json`` file."""

    if not data_dir.exists():
        return []
    result: list[DatasetInfo] = []
    for path in sorted(data_dir.glob("packages_*.json"), key=_dataset_sort_key):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            packages = raw.get("packages", [])
            meta = raw.get("meta", {})
            result.append(
                DatasetInfo(
                    path=path,
                    n_packages=len(packages),
                    seed=meta.get("seed"),
                    error=None,
                )
            )
        except Exception as exc:  # pragma: no cover - malformed user file
            result.append(
                DatasetInfo(path=path, n_packages=None, seed=None, error=str(exc))
            )
    return result


def _schedules_for(
    ctx: PipelineContext, solution: Solution
) -> dict[int, Schedule]:
    """Schedule every courier, including empty routes."""

    routes = {route.courier_id: route.task_ids for route in solution.routes}
    return {
        courier.id: ctx.routing.schedule_route(
            courier.id, routes.get(courier.id, [])
        )
        for courier in ctx.routing.couriers
    }


@dataclass
class UIState:
    root: Path
    campus_path: Path
    config_path: Path
    data_dir: Path
    results_dir: Path
    campus: Campus
    config: dict[str, Any]
    packages_path: Path | None = None
    ctx: PipelineContext | None = None
    couriers: int | None = None
    hard_windows: bool = True
    seed: int = 1
    quick: bool = True
    sorting_method: str = "cap_ls"
    routing_method: str = "alns"
    dataset: DatasetSummary | None = None
    last_sorting: RunRecord | None = None
    last_routing: RunRecord | None = None
    last_solve: RunRecord | None = None
    last_run: RunRecord | None = None
    last_export_path: Path | None = None
    status: str = "就绪"
    status_style: str = "cyan"

    # ------------------------------------------------------------------ setup
    @classmethod
    def create(
        cls,
        *,
        campus: str | Path | None = None,
        config: str | Path | None = None,
        data_dir: str | Path | None = None,
        results_dir: str | Path | None = None,
        root: str | Path | None = None,
    ) -> "UIState":
        repo = Path(root).resolve() if root is not None else find_repo_root()
        campus_path = _resolve_user_path(campus, repo / "data" / "campus.json")
        config_path = _resolve_user_path(config, repo / "config" / "default.yaml")
        data_path = _resolve_user_path(data_dir, repo / "data")
        results_path = _resolve_user_path(results_dir, repo / "results")
        try:
            campus_obj = load_campus(campus_path)
            config_obj = load_config(config_path)
        except Exception as exc:
            raise TUIError(f"无法加载校园/配置：{exc}") from exc
        hard_windows = bool(config_obj.get("routing", {}).get("hard_windows", True))
        seed = int(config_obj.get("project", {}).get("seed", 1))
        return cls(
            root=repo,
            campus_path=campus_path,
            config_path=config_path,
            data_dir=data_path,
            results_dir=results_path,
            campus=campus_obj,
            config=config_obj,
            hard_windows=hard_windows,
            seed=seed,
        )

    def effective_couriers(self) -> int:
        if self.couriers is not None:
            return int(self.couriers)
        return int(self.config["couriers"]["count"])

    @property
    def packages_label(self) -> str:
        return self.packages_path.name if self.packages_path else "未选择"

    @property
    def has_results(self) -> bool:
        return any(
            record is not None
            for record in (self.last_sorting, self.last_routing, self.last_solve)
        )

    def set_status(self, text: str, style: str = "cyan") -> None:
        self.status = text
        self.status_style = style

    def invalidate_results(self) -> None:
        self.last_sorting = None
        self.last_routing = None
        self.last_solve = None
        self.last_run = None
        self.last_export_path = None

    def _require_context(self) -> PipelineContext:
        if self.ctx is None:
            raise TUIError("请先在数据管理中选择或生成数据文件")
        return self.ctx

    # ------------------------------------------------------------------ data
    def autoload_dataset(self) -> None:
        path = choose_default_dataset(self.data_dir)
        if path is None:
            self.set_status("未找到数据文件，请到“数据管理”生成或选择", "yellow")
            return
        try:
            self.select_dataset(path)
        except TUIError as exc:
            self.set_status(str(exc), "red")

    def select_dataset(self, path: str | Path) -> DatasetSummary:
        path = Path(path)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists():
            raise TUIError(f"数据文件不存在：{path}")
        try:
            packages = load_packages(path)
            validate_packages(packages, self.campus)
        except Exception as exc:
            raise TUIError(f"数据文件无效：{exc}") from exc
        count = self.effective_couriers()
        try:
            validation = check_instance(
                packages, self.campus, self.config, couriers_count=count
            )
            ctx = build_context_from_data(
                self.campus,
                self.config,
                packages,
                couriers_count=count,
                hard_windows=self.hard_windows,
            )
        except Exception as exc:
            raise TUIError(f"无法建立求解上下文：{exc}") from exc
        self.packages_path = path
        self.ctx = ctx
        self.dataset = DatasetSummary(
            path=path,
            n_packages=len(packages),
            n_tasks=len(ctx.tasks),
            validation=validation,
        )
        self.invalidate_results()
        if validation.get("feasible", True):
            self.set_status(
                f"已加载 {path.name}：{len(packages)} 件 / {len(ctx.tasks)} 个任务",
                "green",
            )
        else:
            reasons = "；".join(validation.get("reasons", []))
            self.set_status(f"已加载 {path.name}，但容量不可行：{reasons}", "yellow")
        return self.dataset

    def generate_dataset(
        self, n: int, seed: int, out: str | Path | None = None
    ) -> DatasetSummary:
        if n <= 0:
            raise TUIError("包裹数必须为正整数")
        path = Path(out) if out else self.data_dir / f"packages_{n}.json"
        config = copy.deepcopy(self.config)
        count = self.effective_couriers()
        config["couriers"]["count"] = count
        try:
            packages = generate_packages(self.campus, n, seed, config)
            save_dataset(self.campus, packages, n, seed, config, str(path))
        except Exception as exc:
            raise TUIError(f"生成数据失败：{exc}") from exc
        summary = self.select_dataset(path)
        summary.generated = True
        self.dataset = summary
        self.set_status(f"已生成 {path.name}：{n} 件，seed={seed}", "green")
        return summary

    # ------------------------------------------------------------------ settings
    def set_couriers(self, count: int | None) -> int:
        new_count = self.effective_couriers() if count is None else int(count)
        if new_count < 1:
            raise TUIError("快递员数必须大于 0")
        if self.couriers == new_count:
            return new_count
        old = self.couriers
        self.couriers = new_count
        if self.packages_path is None:
            self.set_status(f"快递员数已设为 {new_count}", "green")
            return new_count
        try:
            self.select_dataset(self.packages_path)
        except Exception:
            self.couriers = old
            raise
        feasible = self.dataset.feasible if self.dataset is not None else True
        suffix = "" if feasible else "，容量不可行"
        self.set_status(
            f"快递员数已设为 {new_count}，当前结果已清空{suffix}",
            "green" if feasible else "yellow",
        )
        return new_count

    def set_hard_windows(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if self.hard_windows == enabled:
            return enabled
        old = self.hard_windows
        self.hard_windows = enabled
        if self.packages_path is None:
            self.set_status(
                "时间窗已设为" + ("硬约束" if enabled else "软约束"), "green"
            )
            return enabled
        try:
            self.select_dataset(self.packages_path)
        except Exception:
            self.hard_windows = old
            raise
        feasible = self.dataset.feasible if self.dataset is not None else True
        suffix = "" if feasible else "，容量不可行"
        self.set_status(
            "时间窗已设为"
            + ("硬约束" if enabled else "软约束")
            + "，当前结果已清空"
            + suffix,
            "green" if feasible else "yellow",
        )
        return enabled

    # ------------------------------------------------------------------ runs
    def run_sorting(self, method: str, seed: int) -> RunRecord:
        if method not in SORTING_METHOD_NAMES:
            raise TUIError(f"未知分拣方法：{method}")
        ctx = self._require_context()
        started = time.perf_counter()
        assignment = solve_sorting(ctx, method=method, seed=seed)
        runtime = time.perf_counter() - started
        record = RunRecord(
            kind="sorting",
            method=method,
            seed=seed,
            quick=False,
            runtime_s=runtime,
            created_at=datetime.now(),
            assignment=assignment,
        )
        self.last_sorting = record
        self.last_solve = None
        self.last_run = record
        self.last_export_path = None
        self.sorting_method = method
        self.seed = seed
        self.set_status(
            f"分拣完成：{method}，CV {assignment.load_cv():.3f}，"
            f"用时 {runtime:.2f} s",
            "green",
        )
        return record

    def run_routing(self, method: str, seed: int, quick: bool) -> RunRecord:
        if method not in ROUTING_METHOD_NAMES:
            raise TUIError(f"未知路径方法：{method}")
        ctx = self._require_context()
        started = time.perf_counter()
        solution, alns = solve_routing(
            ctx,
            method=method,
            seed=seed,
            quick=quick,
            time_limit_s=QUICK_ALNS_TIME_LIMIT_S if quick else None,
        )
        runtime = time.perf_counter() - started
        schedules = _schedules_for(ctx, solution)
        record = RunRecord(
            kind="routing",
            method=method,
            seed=seed,
            quick=quick,
            runtime_s=runtime,
            created_at=datetime.now(),
            solution=solution,
            alns=alns,
            schedules=schedules,
        )
        self.last_routing = record
        self.last_solve = None
        self.last_run = record
        self.last_export_path = None
        self.routing_method = method
        self.quick = quick
        self.seed = seed
        metrics = solution.metrics
        self.set_status(
            f"路径完成：{method}，{metrics.get('distance_km', 0.0):.2f} km，"
            f"准时率 {metrics.get('on_time_rate', 0.0) * 100:.1f}%，"
            f"用时 {runtime:.2f} s",
            "green" if metrics.get("feasible", 0.0) else "yellow",
        )
        return record

    def run_solve(
        self,
        sorting_method: str,
        routing_method: str,
        seed: int,
        quick: bool,
    ) -> RunRecord:
        if sorting_method not in SORTING_METHOD_NAMES:
            raise TUIError(f"未知分拣方法：{sorting_method}")
        if routing_method not in ROUTING_METHOD_NAMES:
            raise TUIError(f"未知路径方法：{routing_method}")
        ctx = self._require_context()
        started = time.perf_counter()
        assignment = solve_sorting(ctx, method=sorting_method, seed=seed)
        solution, alns = solve_routing(
            ctx,
            method=routing_method,
            seed=seed,
            quick=quick,
            time_limit_s=QUICK_ALNS_TIME_LIMIT_S if quick else None,
        )
        runtime = time.perf_counter() - started
        schedules = _schedules_for(ctx, solution)
        task_points = {task.id: task.point_id for task in ctx.tasks}
        result = PipelineResult(
            campus=ctx.campus.name,
            n_packages=len(ctx.packages),
            n_tasks=len(ctx.tasks),
            sorting_method=sorting_method,
            routing_method=routing_method,
            sorting=assignment,
            solution=solution,
            runtime_s=runtime,
            alns=alns,
            extra={"schedules": schedules, "task_points": task_points},
        )
        record = RunRecord(
            kind="solve",
            method=f"{sorting_method} + {routing_method}",
            seed=seed,
            quick=quick,
            runtime_s=runtime,
            created_at=datetime.now(),
            assignment=assignment,
            solution=solution,
            alns=alns,
            schedules=schedules,
            result=result,
        )
        self.last_sorting = None
        self.last_routing = None
        self.last_solve = record
        self.last_run = record
        self.last_export_path = None
        self.sorting_method = sorting_method
        self.routing_method = routing_method
        self.seed = seed
        self.quick = quick
        self.set_status(
            f"一键求解完成：{sorting_method} + {routing_method}，"
            f"{solution.metrics.get('distance_km', 0.0):.2f} km，"
            f"用时 {runtime:.2f} s",
            "green" if solution.metrics.get("feasible", 0.0) else "yellow",
        )
        return record

    # ------------------------------------------------------------------ export
    def default_export_path(self) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.results_dir / f"ui_{stamp}.json"

    def export_payload(self) -> dict[str, Any]:
        record = self.last_run
        if record is None:
            raise TUIError("还没有可导出的结果")
        ctx = self.ctx
        if ctx is None:
            raise TUIError("没有可导出的数据上下文")
        stamp = record.created_at.isoformat(timespec="seconds")
        if record.kind == "solve" and record.result is not None:
            payload = record.result.to_dict()
            payload["seed"] = record.seed
            payload["quick"] = record.quick
            payload["created_at"] = stamp
            return payload
        if record.kind == "routing" and record.solution is not None:
            solution = record.solution
            metrics = dict(solution.metrics)
            metrics["n_packages"] = len(ctx.packages)
            metrics["n_tasks"] = len(ctx.tasks)
            metrics["runtime_s"] = record.runtime_s
            if record.alns is not None:
                metrics["alns_iterations"] = record.alns.iterations
            routes = []
            for route in solution.routes:
                schedule = record.schedules.get(route.courier_id)
                routes.append(
                    {
                        "courier_id": route.courier_id,
                        "task_ids": route.task_ids,
                        "point_ids": [
                            ctx.routing.tasks[tid].point_id
                            for tid in route.task_ids
                        ],
                        "load": schedule.load if schedule else 0,
                        "distance_m": schedule.distance_m if schedule else 0.0,
                        "end_time": schedule.end_time if schedule else 0.0,
                    }
                )
            return {
                "campus": ctx.campus.name,
                "n_packages": len(ctx.packages),
                "n_tasks": len(ctx.tasks),
                "method": record.method,
                "seed": record.seed,
                "quick": record.quick,
                "runtime_s": record.runtime_s,
                "created_at": stamp,
                "metrics": metrics,
                "routes": routes,
                "convergence": (
                    record.alns.convergence if record.alns is not None else None
                ),
            }
        if record.kind == "sorting" and record.assignment is not None:
            assignment = record.assignment
            return {
                "campus": ctx.campus.name,
                "n_packages": len(ctx.packages),
                "n_tasks": len(ctx.tasks),
                "method": record.method,
                "sorting_method": record.method,
                "seed": record.seed,
                "runtime_s": record.runtime_s,
                "created_at": stamp,
                "labels": dict(sorted(assignment.labels.items())),
                "loads": assignment.loads,
                "metrics": assignment.metrics,
            }
        raise TUIError("当前结果无法导出")

    def save_last_result(self, path: str | Path | None = None) -> Path:
        payload = self.export_payload()
        target = Path(path) if path is not None else self.default_export_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            target.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            raise TUIError(f"导出失败：{exc}") from exc
        self.last_export_path = target
        self.set_status(f"已导出 {target}", "green")
        return target
