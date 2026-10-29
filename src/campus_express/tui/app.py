"""Interactive Rich console for campus express v2."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, TypeVar

from rich.console import Console
from rich.text import Text

from . import views
from .state import (
    ROUTING_METHODS,
    SORTING_METHODS,
    TUIError,
    UIState,
    discover_datasets,
)

T = TypeVar("T")


class _Quit(Exception):
    """Leave the TUI cleanly."""


class _Back(Exception):
    """Go back one screen."""


class TUIApp:
    def __init__(self, state: UIState, console: Console | None = None) -> None:
        self.state = state
        self.console = console or Console(highlight=False)

    # ------------------------------------------------------------------ loop
    def run(self) -> int:
        while True:
            try:
                self._home()
            except _Quit:
                break
            except _Back:
                continue
            except KeyboardInterrupt:
                self.state.set_status("已取消", "yellow")
            except Exception as exc:  # pragma: no cover - last-resort guard
                self._show_error(exc)
        self.console.clear()
        self.console.print(Text("已退出", style="green"))
        return 0

    def _home(self) -> None:
        self._show(
            views.render_home(self.state, width=self.console.width),
            "数字 + Enter 选择 · q/0 退出",
        )
        choice = self._read("请选择: ")
        if choice == "1":
            self._data_screen()
        elif choice == "2":
            self._sorting_screen()
        elif choice == "3":
            self._routing_screen()
        elif choice == "4":
            self._solve_screen()
        elif choice == "5":
            self._results_screen()
        elif choice == "6":
            self._settings_screen()
        else:
            self.state.set_status(f"无效选项：{choice}", "yellow")

    # ------------------------------------------------------------------ screens
    def _data_screen(self) -> None:
        while True:
            datasets = discover_datasets(self.state.data_dir)
            self._show(
                views.render_dataset_list(datasets, self.state.packages_path),
                "数字 选择 · g 生成 · r 刷新 · b 返回 · q/0 退出",
            )
            choice = self._read("请选择: ")
            key = choice.lower()
            if key == "g":
                if self._generate_flow():
                    return
                continue
            if key == "r":
                continue
            try:
                index = int(choice)
            except ValueError:
                self.state.set_status(f"无效选项：{choice}", "yellow")
                continue
            if not 1 <= index <= len(datasets):
                self.state.set_status(f"编号超出范围：{index}", "yellow")
                continue
            summary = self._run_with_status(
                "加载数据",
                lambda info=datasets[index - 1]: self.state.select_dataset(info.path),
            )
            if summary is None:
                continue
            self._show(
                views.render_validation(summary),
                "Enter 返回 · q/0 退出",
            )
            self._pause()
            return

    def _generate_flow(self) -> bool:
        try:
            n = self._ask_int("包裹数", 300, 1, 5000)
            seed = self._ask_int("随机种子", self.state.seed, 1, 10**9)
            default = self.state.data_dir / f"packages_{n}.json"
            path = self._ask_path("输出文件", default)
            if path.exists() and not self._ask_yes_no(
                f"{path.name} 已存在，覆盖?", False
            ):
                return False
        except _Back:
            return False
        summary = self._run_with_status(
            "生成数据",
            lambda: self.state.generate_dataset(n, seed, path),
        )
        if summary is None:
            return False
        self._show(
            views.render_validation(summary),
            "Enter 返回 · q/0 退出",
        )
        self._pause()
        return True

    def _sorting_screen(self) -> None:
        if self.state.ctx is None:
            self.state.set_status("请先在数据管理中选择或生成数据文件", "yellow")
            self._pause()
            return
        while True:
            self._show(
                views.render_method_menu("sorting", self.state.sorting_method),
                "数字 选择 · b 返回 · q/0 退出",
            )
            choice = self._read("选择分拣方法: ")
            try:
                index = int(choice)
            except ValueError:
                self.state.set_status(f"无效选项：{choice}", "yellow")
                continue
            if not 1 <= index <= len(SORTING_METHODS):
                self.state.set_status(f"编号超出范围：{index}", "yellow")
                continue
            method = SORTING_METHODS[index - 1][0]
            try:
                seed = self._ask_int("随机种子", self.state.seed, 1, 10**9)
            except _Back:
                continue
            record = self._run_with_status(
                "运行分拣",
                lambda: self.state.run_sorting(method, seed),
            )
            if record is None:
                continue
            self._show(
                views.render_sorting_result(self.state.ctx, record),
                "Enter 返回 · q/0 退出",
            )
            self._pause()
            return

    def _routing_screen(self) -> None:
        if self.state.ctx is None:
            self.state.set_status("请先在数据管理中选择或生成数据文件", "yellow")
            self._pause()
            return
        while True:
            self._show(
                views.render_method_menu("routing", self.state.routing_method),
                "数字 选择 · k 切换快速 · b 返回 · q/0 退出",
            )
            choice = self._read("选择路径方法: ")
            if choice.lower() == "k":
                self.state.quick = not self.state.quick
                self.state.set_status(
                    "快速模式已" + ("开启" if self.state.quick else "关闭"),
                    "green",
                )
                continue
            try:
                index = int(choice)
            except ValueError:
                self.state.set_status(f"无效选项：{choice}", "yellow")
                continue
            if not 1 <= index <= len(ROUTING_METHODS):
                self.state.set_status(f"编号超出范围：{index}", "yellow")
                continue
            method = ROUTING_METHODS[index - 1][0]
            try:
                seed = self._ask_int("随机种子", self.state.seed, 1, 10**9)
            except _Back:
                continue
            record = self._run_with_status(
                "运行路径",
                lambda: self.state.run_routing(method, seed, self.state.quick),
            )
            if record is None:
                continue
            self._show(
                views.render_routing_result(self.state.ctx, record),
                "Enter 返回 · q/0 退出",
            )
            self._pause()
            return

    def _solve_screen(self) -> None:
        if self.state.ctx is None:
            self.state.set_status("请先在数据管理中选择或生成数据文件", "yellow")
            self._pause()
            return
        while True:
            self._show(
                views.render_solve_confirm(self.state),
                "Enter 开始 · b 返回 · q/0 退出",
            )
            choice = self._read("开始一键求解? ")
            if choice:
                return
            record = self._run_with_status(
                "一键求解（分拣 + 路径）",
                lambda: self.state.run_solve(
                    self.state.sorting_method,
                    self.state.routing_method,
                    self.state.seed,
                    self.state.quick,
                ),
            )
            if record is None:
                continue
            self._show(
                views.render_solve_result(self.state.ctx, record),
                "Enter 返回 · q/0 退出",
            )
            self._pause()
            return

    def _results_screen(self) -> None:
        if self.state.ctx is None or not self.state.has_results:
            self.state.set_status("还没有结果；先运行分拣、路径或一键求解", "yellow")
            self._pause()
            return
        while True:
            self._show(
                views.render_results(self.state),
                "1 路线明细 · 2 导出 · b 返回 · q/0 退出",
            )
            choice = self._read("请选择: ")
            if choice == "1":
                record = self.state.last_solve or self.state.last_routing
                if record is None:
                    self.state.set_status("当前只有分拣结果，没有路线明细", "yellow")
                    continue
                try:
                    courier = self._ask_int(
                        "快递员编号",
                        1,
                        1,
                        self.state.effective_couriers(),
                    )
                except _Back:
                    continue
                self._show(
                    views.render_route_detail(
                        self.state.ctx, record, courier - 1
                    ),
                    "Enter 返回 · q/0 退出",
                )
                self._pause()
            elif choice == "2":
                self._export_flow()
            else:
                self.state.set_status(f"无效选项：{choice}", "yellow")

    def _settings_screen(self) -> None:
        while True:
            self._show(
                views.render_settings(self.state),
                "1 导出 · 2 快递员 · 3 种子 · 4 快速 · 5 时间窗 · b 返回",
            )
            choice = self._read("请选择: ")
            if choice == "1":
                self._export_flow()
            elif choice == "2":
                try:
                    count = self._ask_int(
                        "快递员数", self.state.effective_couriers(), 1, 10
                    )
                except _Back:
                    continue
                self._guard(lambda: self.state.set_couriers(count))
            elif choice == "3":
                try:
                    seed = self._ask_int("随机种子", self.state.seed, 1, 10**9)
                except _Back:
                    continue
                self.state.seed = seed
                self.state.set_status(f"随机种子已设为 {seed}", "green")
            elif choice == "4":
                self.state.quick = not self.state.quick
                self.state.set_status(
                    "快速模式已" + ("开启" if self.state.quick else "关闭"),
                    "green",
                )
            elif choice == "5":
                self._guard(
                    lambda: self.state.set_hard_windows(
                        not self.state.hard_windows
                    )
                )
            else:
                self.state.set_status(f"无效选项：{choice}", "yellow")

    def _export_flow(self) -> None:
        if not self.state.has_results:
            self.state.set_status("还没有可导出的结果", "yellow")
            return
        default = self.state.default_export_path()
        try:
            path = self._ask_path("导出路径", default)
            if path.exists() and not self._ask_yes_no(
                f"{path.name} 已存在，覆盖?", False
            ):
                return
        except _Back:
            return
        result = self._run_with_status(
            "导出结果",
            lambda: self.state.save_last_result(path),
        )
        if result is not None:
            self._pause()

    # ------------------------------------------------------------------ helpers
    def _show(self, body, footer: str) -> None:
        self.console.clear()
        self.console.print(views.render_header(self.state))
        self.console.print(views.render_status_bar(self.state))
        self.console.print(body)
        self.console.print(views.render_footer(footer))

    def _read(self, prompt: str = "请选择: ") -> str:
        self.console.print(Text(prompt, style="bold cyan"), end="")
        try:
            raw = input().strip()
        except (EOFError, KeyboardInterrupt):
            self.console.print()
            raise _Quit
        key = raw.lower()
        if key in {"q", "quit", "exit", "0"}:
            raise _Quit
        if key in {"b", "back"}:
            raise _Back
        return raw

    def _ask_int(
        self,
        prompt: str,
        default: int,
        minimum: int = 1,
        maximum: int | None = None,
    ) -> int:
        while True:
            raw = self._read(f"{prompt} [{default}]: ")
            if raw == "":
                if default < minimum or (
                    maximum is not None and default > maximum
                ):
                    return minimum
                return default
            try:
                value = int(raw)
            except ValueError:
                self.console.print(Text("请输入整数。", style="red"))
                continue
            if value < minimum or (maximum is not None and value > maximum):
                upper = "∞" if maximum is None else str(maximum)
                self.console.print(
                    Text(f"请输入 {minimum} 到 {upper} 之间的整数。", style="red")
                )
                continue
            return value

    def _ask_yes_no(self, prompt: str, default: bool = False) -> bool:
        suffix = "Y/n" if default else "y/N"
        while True:
            raw = self._read(f"{prompt} [{suffix}]: ")
            if raw == "":
                return default
            key = raw.lower()
            if key in {"y", "yes"}:
                return True
            if key in {"n", "no"}:
                return False
            self.console.print(Text("请输入 y 或 n。", style="red"))

    def _ask_path(self, prompt: str, default: Path) -> Path:
        raw = self._read(f"{prompt} [{default}]: ")
        return Path(raw) if raw else Path(default)

    def _pause(self, text: str = "按 Enter 继续") -> None:
        try:
            self._read(f"{text}: ")
        except _Back:
            pass

    def _show_error(self, exc: BaseException) -> None:
        message = str(exc) or exc.__class__.__name__
        self.state.set_status(message, "red")

    def _guard(self, func: Callable[[], T]) -> T | None:
        try:
            return func()
        except (_Back, _Quit):
            raise
        except Exception as exc:
            self._show_error(exc)
            return None

    def _run_with_status(self, label: str, func: Callable[[], T]) -> T | None:
        try:
            with self.console.status(f"[cyan]{label}...[/]", spinner="dots"):
                return func()
        except (_Back, _Quit):
            raise
        except KeyboardInterrupt:
            self.state.set_status("已取消", "yellow")
            return None
        except Exception as exc:
            self._show_error(exc)
            return None


def run_tui(
    campus: str | Path | None = None,
    config: str | Path | None = None,
    packages: str | Path | None = None,
    data_dir: str | Path | None = None,
    results_dir: str | Path | None = None,
    couriers: int | None = None,
    seed: int | None = None,
    quick: bool = True,
    console: Console | None = None,
) -> int:
    ui_console = console or Console(highlight=False)
    try:
        state = UIState.create(
            campus=campus,
            config=config,
            data_dir=data_dir,
            results_dir=results_dir,
        )
    except Exception as exc:
        ui_console.print(views.render_error(str(exc)))
        return 1
    if couriers is not None:
        if int(couriers) < 1:
            ui_console.print(views.render_error("快递员数必须大于 0"))
            return 1
        state.couriers = int(couriers)
    if seed is not None:
        state.seed = int(seed)
    state.quick = bool(quick)
    if packages is not None:
        try:
            state.select_dataset(packages)
        except TUIError as exc:
            state.set_status(str(exc), "red")
    else:
        state.autoload_dataset()
    return TUIApp(state, ui_console).run()
