from __future__ import annotations

import json
import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from campus_express.data_gen import check_instance
from campus_express.io import load_campus, load_config, load_packages
from campus_express.routing.alns import ALNSResult
from campus_express.tui import views
from campus_express.tui.app import TUIApp, run_tui
from campus_express.tui.state import (
    TUIError,
    UIState,
    choose_default_dataset,
    discover_datasets,
    find_repo_root,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tui_state(tmp_path):
    state = UIState.create(
        campus=ROOT / "data" / "campus.json",
        config=ROOT / "config" / "default.yaml",
        data_dir=tmp_path,
        results_dir=tmp_path / "results",
        root=ROOT,
    )
    state.generate_dataset(20, seed=5, out=tmp_path / "packages_20.json")
    return state


def _console() -> Console:
    return Console(
        file=StringIO(),
        width=120,
        force_terminal=False,
        color_system=None,
        highlight=False,
    )


def test_find_repo_root_returns_project_root():
    root = find_repo_root(ROOT / "run.py")
    assert (root / "data" / "campus.json").exists()
    assert (root / "config" / "default.yaml").exists()


def test_choose_default_dataset_prefers_300(tmp_path):
    (tmp_path / "packages_100.json").write_text("{}", encoding="utf-8")
    (tmp_path / "packages_300.json").write_text("{}", encoding="utf-8")
    assert choose_default_dataset(tmp_path).name == "packages_300.json"


def test_discover_datasets_reports_counts_and_malformed(tmp_path):
    (tmp_path / "packages_10.json").write_text(
        json.dumps({"packages": [{}, {}, {}]}), encoding="utf-8"
    )
    (tmp_path / "packages_20.json").write_text("{bad json", encoding="utf-8")
    infos = discover_datasets(tmp_path)
    assert len(infos) == 2
    assert infos[0].n_packages == 3
    assert infos[0].path.name == "packages_10.json"
    assert infos[1].error


def test_select_dataset_builds_context(tui_state):
    assert tui_state.ctx is not None
    assert len(tui_state.ctx.packages) == 20
    assert len(tui_state.ctx.tasks) > 0
    assert tui_state.dataset is not None
    assert tui_state.dataset.structurally_valid
    assert tui_state.dataset.feasible


def test_select_dataset_failure_keeps_previous(tui_state, tmp_path):
    old_path = tui_state.packages_path
    old_ctx = tui_state.ctx
    bad = tmp_path / "packages_bad.json"
    bad.write_text("{bad json", encoding="utf-8")
    with pytest.raises(TUIError):
        tui_state.select_dataset(bad)
    assert tui_state.packages_path == old_path
    assert tui_state.ctx is old_ctx


def test_generate_dataset_writes_and_activates(tui_state, tmp_path):
    path = tmp_path / "packages_20.json"
    assert path.exists()
    assert tui_state.packages_path == path
    assert tui_state.dataset is not None and tui_state.dataset.generated
    assert len(load_packages(path)) == 20


def test_run_sorting_grid_records_assignment(tui_state):
    record = tui_state.run_sorting("grid", 1)
    assert record.assignment is not None
    assert len(record.assignment.loads) == 10
    assert sum(record.assignment.loads) == 20
    assert tui_state.last_sorting is record
    assert tui_state.last_run is record


def test_run_routing_nn_records_every_courier(tui_state):
    record = tui_state.run_routing("nn", 1, True)
    assert record.solution is not None
    assert record.solution.metrics["unassigned"] == 0
    assert record.solution.metrics["feasible"] == 1.0
    assert len(record.schedules) == tui_state.effective_couriers()
    assert tui_state.last_routing is record


def test_run_solve_builds_pipeline_result(tui_state):
    record = tui_state.run_solve("grid", "nn", 1, True)
    assert record.result is not None
    payload = record.result.to_dict()
    assert payload["n_packages"] == 20
    assert "sorting" in payload
    assert "routes" in payload
    assert "metrics" in payload
    assert len(record.schedules) == tui_state.effective_couriers()


def test_set_couriers_rebuilds_and_invalidates(tui_state):
    tui_state.run_sorting("grid", 1)
    assert tui_state.last_sorting is not None
    tui_state.set_couriers(6)
    assert tui_state.couriers == 6
    assert tui_state.ctx is not None
    assert len(tui_state.ctx.routing.couriers) == 6
    assert tui_state.last_sorting is None


def test_set_invalid_couriers_raises(tui_state):
    old = tui_state.couriers
    with pytest.raises(TUIError):
        tui_state.set_couriers(0)
    assert tui_state.couriers == old


def test_set_hard_windows_rebuilds_context(tui_state):
    assert tui_state.ctx is not None
    assert tui_state.ctx.routing.hard_windows is True
    tui_state.set_hard_windows(False)
    assert tui_state.ctx is not None
    assert tui_state.ctx.routing.hard_windows is False


def test_export_sorting_payload(tui_state, tmp_path):
    tui_state.run_sorting("grid", 1)
    target = tui_state.save_last_result(tmp_path / "sorting.json")
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["method"] == "grid"
    assert payload["n_packages"] == 20
    assert "labels" in payload
    assert "loads" in payload
    assert "metrics" in payload


def test_save_last_result_inspect_compatible(tui_state, tmp_path):
    tui_state.run_solve("grid", "nn", 1, True)
    target = tui_state.save_last_result(tmp_path / "ui.json")
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["n_packages"] == 20
    assert "metrics" in payload
    assert "sorting" in payload
    assert "routes" in payload
    assert tui_state.last_export_path == target


def test_check_instance_honours_courier_override():
    campus = load_campus(ROOT / "data" / "campus.json")
    config = load_config(ROOT / "config" / "default.yaml")
    packages = load_packages(ROOT / "data" / "packages_100.json")
    four = check_instance(packages, campus, config, couriers_count=4)
    one = check_instance(packages, campus, config, couriers_count=1)
    assert four["courier_capacity_packages"] == 4 * 160
    assert one["courier_capacity_packages"] == 160


def test_render_home_shows_menu_and_status(tui_state):
    console = _console()
    console.print(views.render_header(tui_state))
    console.print(views.render_status_bar(tui_state))
    console.print(views.render_home(tui_state, width=120))
    text = console.file.getvalue()
    assert "数据管理" in text
    assert "一键求解" in text
    assert "packages_20.json" in text
    assert "cap_ls" in text


def test_render_sorting_result_lists_all_chutes(tui_state):
    record = tui_state.run_sorting("grid", 1)
    console = _console()
    console.print(views.render_sorting_result(tui_state.ctx, record))
    text = console.file.getvalue()
    assert "C01" in text
    assert "C10" in text
    assert "容量比" in text
    assert "格口负载" in text


def test_render_routing_result_lists_couriers(tui_state):
    record = tui_state.run_routing("nn", 1, True)
    console = _console()
    console.print(views.render_routing_result(tui_state.ctx, record))
    text = console.file.getvalue()
    assert "快递员" in text
    assert "停靠" in text
    assert "距离" in text
    assert "结束" in text


def test_render_route_detail_contains_tasks(tui_state):
    record = tui_state.run_routing("nn", 1, True)
    route = next(route for route in record.solution.routes if route.task_ids)
    task = tui_state.ctx.routing.tasks[route.task_ids[0]]
    point_name = tui_state.ctx.campus.points[task.point_id].name
    console = _console()
    console.print(views.render_route_detail(tui_state.ctx, record, route.courier_id))
    text = console.file.getvalue()
    assert point_name in text
    assert "时间窗" in text
    assert "优先级" in text


def test_render_results_shows_alns_convergence(tui_state):
    record = tui_state.run_routing("nn", 1, True)
    record.alns = ALNSResult(
        best=record.solution,
        convergence=[10.0, 9.0, 8.0],
        runtime_s=1.2,
        iterations=3,
        operator_stats={},
    )
    console = _console()
    console.print(views.render_routing_result(tui_state.ctx, record))
    text = console.file.getvalue()
    assert "ALNS 收敛" in text
    assert "迭代" in text
    assert "改进" in text


def test_sparkline_handles_empty_constant_and_downsampling():
    assert views.sparkline([]) == ""
    assert len(set(views.sparkline([5.0, 5.0, 5.0]))) == 1
    line = views.sparkline(list(range(100)), width=20)
    assert len(line) == 20


def test_render_settings_shows_current_values(tui_state):
    console = _console()
    console.print(views.render_settings(tui_state))
    text = console.file.getvalue()
    assert "快递员数" in text
    assert "快速模式" in text
    assert "时间窗" in text
    assert "结果" in text


def test_app_quits_on_q(tui_state, monkeypatch):
    console = _console()
    monkeypatch.setattr("builtins.input", lambda: "q")
    app = TUIApp(tui_state, console)
    assert app.run() == 0
    assert "已退出" in console.file.getvalue()


def test_app_bad_menu_input_does_not_crash(tui_state, monkeypatch):
    console = _console()
    inputs = iter(["9", "q"])
    monkeypatch.setattr("builtins.input", lambda: next(inputs))
    app = TUIApp(tui_state, console)
    assert app.run() == 0
    assert "无效选项" in console.file.getvalue()


def test_run_tui_missing_config_returns_error_code(tmp_path):
    console = _console()
    code = run_tui(config=tmp_path / "missing.yaml", console=console)
    assert code == 1
    assert "错误" in console.file.getvalue()


def test_cli_ui_help():
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "run.py"), "ui", "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--packages" in proc.stdout


def test_cli_no_args_starts_tui_and_quits(tmp_path):
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "run.py")],
        cwd=tmp_path,
        input="q\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert "校园快递" in proc.stdout
    assert "Traceback" not in proc.stdout
